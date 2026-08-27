import Foundation
import AppKit
import Photos

let isoFormatter = ISO8601DateFormatter()
isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

func commandLineOptionValue(_ name: String) -> String? {
    let arguments = CommandLine.arguments
    guard let index = arguments.firstIndex(of: name) else {
        return nil
    }
    let valueIndex = arguments.index(after: index)
    guard valueIndex < arguments.endIndex else {
        return nil
    }
    return arguments[valueIndex]
}

let inputJSONFilePath = commandLineOptionValue("--input-json-file")
let outputJSONFilePath = commandLineOptionValue("--output-json-file")

// Coerce any value into a JSON-safe type so JSONSerialization can never throw.
// PhotoKit-derived payloads are built from String/Int/Bool/[String:Any]/[Any]
// already, but this walks defensively: dates become ISO8601 strings, non-finite
// Doubles are dropped, non-string keys are stringified, and unknown types fall
// back to their description. Anything that still cannot be represented is dropped.
func sanitizeForJSON(_ value: Any) -> Any? {
    switch value {
    case is NSNull:
        return value
    case let string as String:
        return string
    case let number as NSNumber:
        // NSNumber covers Bool/Int/Double bridged from Swift. Guard non-finite Doubles.
        let doubleValue = number.doubleValue
        if !doubleValue.isFinite {
            return nil
        }
        return number
    case let boolValue as Bool:
        return boolValue
    case let intValue as Int:
        return intValue
    case let doubleValue as Double:
        return doubleValue.isFinite ? doubleValue : nil
    case let date as Date:
        return isoFormatter.string(from: date)
    case let array as [Any]:
        return array.compactMap { sanitizeForJSON($0) }
    case let dictionary as [String: Any]:
        var sanitized: [String: Any] = [:]
        for (key, element) in dictionary {
            if let sanitizedElement = sanitizeForJSON(element) {
                sanitized[key] = sanitizedElement
            }
        }
        return sanitized
    case let dictionary as [AnyHashable: Any]:
        var sanitized: [String: Any] = [:]
        for (key, element) in dictionary {
            if let sanitizedElement = sanitizeForJSON(element) {
                sanitized["\(key)"] = sanitizedElement
            }
        }
        return sanitized
    default:
        return String(describing: value)
    }
}

// Serialize the payload, sanitizing on failure, and never trap. Returns nil only
// if even the minimal fallback error payload cannot be encoded (should be impossible).
func serializePayload(_ payload: [String: Any]) -> Data? {
    if JSONSerialization.isValidJSONObject(payload) {
        if let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]) {
            return data
        }
    }
    let sanitized = sanitizeForJSON(payload)
    if let sanitizedDict = sanitized as? [String: Any],
       JSONSerialization.isValidJSONObject(sanitizedDict),
       let data = try? JSONSerialization.data(withJSONObject: sanitizedDict, options: [.sortedKeys]) {
        return data
    }
    let fallback: [String: Any] = [
        "schema_version": 1,
        "status": "error",
        "source": "photos",
        "warnings": [
            [
                "code": "photos_output_serialization_failed",
                "message": "Photos helper output could not be serialized to JSON.",
            ]
        ],
    ]
    return try? JSONSerialization.data(withJSONObject: fallback, options: [.sortedKeys])
}

func emit(_ payload: [String: Any]) -> Never {
    // Serialization is best-effort and can never trap: a non-serializable payload
    // degrades to a guaranteed-serializable error JSON via serializePayload.
    let data = serializePayload(payload) ?? Data("{\"schema_version\":1,\"status\":\"error\",\"source\":\"photos\"}".utf8)

    // Best-effort file write. If the output directory has been deleted (the cold-start
    // timeout race, where Python's TemporaryDirectory context has already exited), do
    // NOT trap: fall through to stdout and exit with a nonzero code so the Python side
    // treats the run as degraded rather than crashing with SIGTRAP.
    if let outputJSONFilePath {
        do {
            try data.write(to: URL(fileURLWithPath: outputJSONFilePath))
            exit(0)
        } catch {
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write(Data("\n".utf8))
            exit(1)
        }
    }
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
    exit(0)
}

func warning(_ code: String, _ message: String) -> [String: String] {
    return ["code": code, "message": message]
}

func intValue(_ request: [String: Any], _ key: String, _ defaultValue: Int) -> Int {
    if let value = request[key] as? Int {
        return value
    }
    if let value = request[key] as? Double {
        return Int(value)
    }
    return defaultValue
}

func stringValue(_ request: [String: Any], _ key: String) -> String {
    return (request[key] as? String) ?? ""
}

func authorizationStatus() -> PHAuthorizationStatus {
    if #available(macOS 11.0, *) {
        return PHPhotoLibrary.authorizationStatus(for: .readWrite)
    }
    return PHPhotoLibrary.authorizationStatus()
}

func authorizationName(_ status: PHAuthorizationStatus) -> String {
    switch status {
    case .authorized:
        return "authorized"
    case .limited:
        return "limited"
    case .denied:
        return "denied"
    case .notDetermined:
        return "not_determined"
    case .restricted:
        return "restricted"
    @unknown default:
        return "unknown"
    }
}

func readAuthorized(_ status: PHAuthorizationStatus) -> Bool {
    switch status {
    case .authorized, .limited:
        return true
    default:
        return false
    }
}

func fullLibraryAuthorized(_ status: PHAuthorizationStatus) -> Bool {
    switch status {
    case .authorized:
        return true
    default:
        return false
    }
}

func requestResultName(_ status: PHAuthorizationStatus) -> String {
    switch status {
    case .authorized:
        return "granted"
    case .limited:
        return "limited"
    case .denied:
        return "not_granted"
    case .notDetermined:
        return "not_determined"
    case .restricted:
        return "restricted"
    @unknown default:
        return "unknown"
    }
}

func activateForPhotosPrompt() {
    NSApplication.shared.setActivationPolicy(.regular)
    NSApplication.shared.finishLaunching()
    NSApplication.shared.activate(ignoringOtherApps: true)
}

func requestPhotosFullAccess() {
    let initialStatus = authorizationStatus()
    if fullLibraryAuthorized(initialStatus) {
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": authorizationName(initialStatus),
            "request_result": "already_authorized",
            "warnings": [],
        ])
    }

    var completed = false
    var finalStatus = initialStatus

    activateForPhotosPrompt()

    if #available(macOS 11.0, *) {
        PHPhotoLibrary.requestAuthorization(for: .readWrite) { status in
            finalStatus = status
            completed = true
        }
    } else {
        PHPhotoLibrary.requestAuthorization { status in
            finalStatus = status
            completed = true
        }
    }

    let deadline = Date().addingTimeInterval(180)
    while !completed && Date() < deadline {
        _ = RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.1))
    }

    if !completed {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "photos",
            "authorization_status": authorizationName(authorizationStatus()),
            "request_result": "timeout",
            "warnings": [warning("photos_access_request_timeout", "Photos access prompt did not complete before timeout.")],
        ])
    }

    if fullLibraryAuthorized(finalStatus) {
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": authorizationName(finalStatus),
            "request_result": requestResultName(finalStatus),
            "warnings": [],
        ])
    }

    let accessWarning: [String: String]
    if finalStatus == .limited {
        accessWarning = warning(
            "photos_full_access_required",
            "Photos full library access was not granted to this process."
        )
    } else {
        accessWarning = warning("photos_access_unavailable", "Photos access was not granted to this process.")
    }
    emit([
        "schema_version": 1,
        "status": "degraded",
        "source": "photos",
        "authorization_status": authorizationName(finalStatus),
        "request_result": requestResultName(finalStatus),
        "warnings": [accessWarning],
    ])
}

func ensureAccess() {
    let status = authorizationStatus()
    if !readAuthorized(status) {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "assets": [],
            "asset": NSNull(),
            "warnings": [
                warning(
                    "photos_access_unavailable",
                    "Photos access is not authorized for this process."
                )
            ],
        ])
    }
}

func applyAccessUnavailablePayload() -> [String: Any] {
    let status = authorizationStatus()
    return [
        "schema_version": 1,
        "status": "degraded",
        "source": "photos",
        "authorization_status": authorizationName(status),
        "asset": NSNull(),
        "warnings": [
            warning(
                "photos_access_unavailable",
                "Photos access is not authorized for this process."
            )
        ],
    ]
}

func albumManagementAccessUnavailablePayload(_ status: PHAuthorizationStatus) -> [String: Any] {
    return [
        "schema_version": 1,
        "status": "degraded",
        "source": "photos",
        "authorization_status": authorizationName(status),
        "album": NSNull(),
        "warnings": [
            warning(
                "photos_full_access_required",
                "Photos album management requires full Photos Library access."
            )
        ],
    ]
}

func mediaTypeName(_ asset: PHAsset) -> String {
    switch asset.mediaType {
    case .image:
        return "image"
    case .video:
        return "video"
    case .audio:
        return "audio"
    case .unknown:
        return "unknown"
    @unknown default:
        return "unknown"
    }
}

func resourcePayload(_ resource: PHAssetResource) -> [String: Any] {
    return [
        "filename": resource.originalFilename,
        "type": resource.type.rawValue,
        "uniform_type_identifier": resource.uniformTypeIdentifier,
    ]
}

func sanitizedFilename(_ requested: String, fallback: String) -> String {
    let fallbackName = URL(fileURLWithPath: fallback.isEmpty ? "photo-asset" : fallback).lastPathComponent
    var candidate = URL(fileURLWithPath: requested.isEmpty ? fallbackName : requested).lastPathComponent
    if candidate.isEmpty {
        candidate = fallbackName
    }

    let fallbackExtension = URL(fileURLWithPath: fallbackName).pathExtension
    if URL(fileURLWithPath: candidate).pathExtension.isEmpty && !fallbackExtension.isEmpty {
        candidate += ".\(fallbackExtension)"
    }

    let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    let scalars = candidate.unicodeScalars.map { allowed.contains($0) ? Character($0) : "-" }
    var safe = String(scalars).trimmingCharacters(in: CharacterSet(charactersIn: ".-_"))
    if safe.isEmpty {
        safe = "photo-asset"
        if !fallbackExtension.isEmpty {
            safe += ".\(fallbackExtension)"
        }
    }
    if safe.count > 160 {
        safe = String(safe.prefix(160))
    }
    return safe
}

func uniqueOutputURL(directory: URL, filename: String) throws -> URL {
    let manager = FileManager.default
    let first = directory.appendingPathComponent(filename, isDirectory: false)
    if !manager.fileExists(atPath: first.path) {
        return first
    }
    let url = URL(fileURLWithPath: filename)
    let stem = url.deletingPathExtension().lastPathComponent
    let ext = url.pathExtension
    for index in 1..<1000 {
        let candidateName = ext.isEmpty ? "\(stem)-\(index)" : "\(stem)-\(index).\(ext)"
        let candidate = directory.appendingPathComponent(candidateName, isDirectory: false)
        if !manager.fileExists(atPath: candidate.path) {
            return candidate
        }
    }
    throw NSError(domain: "local-apple-data", code: 1)
}

func resources(_ asset: PHAsset) -> [PHAssetResource] {
    return PHAssetResource.assetResources(for: asset)
}

func primaryFilename(_ asset: PHAsset) -> String {
    return resources(asset).first?.originalFilename ?? ""
}

func matches(_ asset: PHAsset, query: String, mediaType: String) -> Bool {
    if !mediaType.isEmpty && mediaType != "all" && mediaType != mediaTypeName(asset) {
        return false
    }
    if query.isEmpty {
        return true
    }
    return resources(asset).contains {
        $0.originalFilename.lowercased().contains(query)
    }
}

func assetPayload(_ asset: PHAsset, includeResources: Bool) -> [String: Any] {
    var payload: [String: Any] = [
        "asset_id": asset.localIdentifier,
        "media_type": mediaTypeName(asset),
        "media_subtypes": asset.mediaSubtypes.rawValue,
        "pixel_width": asset.pixelWidth,
        "pixel_height": asset.pixelHeight,
        "duration": asset.duration,
        "favorite": asset.isFavorite,
        "hidden": asset.isHidden,
        "source_type": asset.sourceType.rawValue,
        "creation_date": asset.creationDate.map { isoFormatter.string(from: $0) } ?? "",
        "modification_date": asset.modificationDate.map { isoFormatter.string(from: $0) } ?? "",
        "primary_filename": primaryFilename(asset),
        "resource_count": resources(asset).count,
        "asset_content_returned": false,
    ]
    if includeResources {
        payload["resources"] = resources(asset).map { resourcePayload($0) }
    }
    return payload
}

func albumAssets(_ album: PHAssetCollection) -> PHFetchResult<PHAsset> {
    return PHAsset.fetchAssets(in: album, options: nil)
}

func albumAssetCount(_ album: PHAssetCollection) -> Int {
    return albumAssets(album).count
}

func albumPayload(_ album: PHAssetCollection) -> [String: Any] {
    return [
        "album_id": album.localIdentifier,
        "title": album.localizedTitle ?? "",
        "asset_collection_type": album.assetCollectionType.rawValue,
        "asset_collection_subtype": album.assetCollectionSubtype.rawValue,
        "estimated_asset_count": album.estimatedAssetCount == NSNotFound ? -1 : Int(album.estimatedAssetCount),
        "asset_count": albumAssetCount(album),
        "can_add_content": album.canPerform(.addContent),
        "can_remove_content": album.canPerform(.removeContent),
        "can_rename": album.canPerform(.rename),
        "can_delete": album.canPerform(.delete),
        "raw_album_identifier_returned": false,
    ]
}

func isRegularAlbum(_ album: PHAssetCollection) -> Bool {
    return album.assetCollectionType == .album && album.assetCollectionSubtype == .albumRegular
}

func albumMatches(_ album: PHAssetCollection, query: String) -> Bool {
    if query.isEmpty {
        return true
    }
    return (album.localizedTitle ?? "").lowercased().contains(query)
}

func fetchAlbumById(_ albumId: String) -> PHAssetCollection? {
    let fetched = PHAssetCollection.fetchAssetCollections(withLocalIdentifiers: [albumId], options: nil)
    guard let album = fetched.firstObject, isRegularAlbum(album) else {
        return nil
    }
    return album
}

func albumContainsAsset(_ album: PHAssetCollection, assetId: String) -> Bool {
    let assets = albumAssets(album)
    var found = false
    assets.enumerateObjects { asset, _, stop in
        if asset.localIdentifier == assetId {
            found = true
            stop.pointee = true
        }
    }
    return found
}

func albumStatePayload(_ album: PHAssetCollection) -> [String: Any] {
    return [
        "title": album.localizedTitle ?? "",
        "asset_collection_type": album.assetCollectionType.rawValue,
        "asset_collection_subtype": album.assetCollectionSubtype.rawValue,
        "asset_count": albumAssetCount(album),
        "can_add_content": album.canPerform(.addContent),
        "can_remove_content": album.canPerform(.removeContent),
    ]
}

func isValidAlbumTitle(_ title: String) -> Bool {
    let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
    return !trimmed.isEmpty && trimmed == title && title.count <= 200
}

func fetchAlbumWithExactTitle(_ title: String, excludingAlbumId: String = "") -> PHAssetCollection? {
    let fetched = PHAssetCollection.fetchAssetCollections(with: .album, subtype: .albumRegular, options: nil)
    var found: PHAssetCollection? = nil
    fetched.enumerateObjects { album, _, stop in
        if (album.localizedTitle ?? "") == title && album.localIdentifier != excludingAlbumId {
            found = album
            stop.pointee = true
        }
    }
    return found
}

func deleteStatePayload(_ asset: PHAsset) -> [String: Any] {
    return [
        "media_type": mediaTypeName(asset),
        "media_subtypes": asset.mediaSubtypes.rawValue,
        "pixel_width": asset.pixelWidth,
        "pixel_height": asset.pixelHeight,
        "duration": asset.duration,
        "favorite": asset.isFavorite,
        "hidden": asset.isHidden,
        "source_type": asset.sourceType.rawValue,
        "creation_date": asset.creationDate.map { isoFormatter.string(from: $0) } ?? "",
        "modification_date": asset.modificationDate.map { isoFormatter.string(from: $0) } ?? "",
        "primary_filename": primaryFilename(asset),
        "resource_count": resources(asset).count,
    ]
}

func numericValue(_ value: Any?) -> Double? {
    if value is Bool {
        return nil
    }
    if let value = value as? Int {
        return Double(value)
    }
    if let value = value as? UInt {
        return Double(value)
    }
    if let value = value as? Int64 {
        return Double(value)
    }
    if let value = value as? UInt64 {
        return Double(value)
    }
    if let value = value as? Double {
        return value
    }
    if let value = value as? Float {
        return Double(value)
    }
    if let value = value as? NSNumber {
        return value.doubleValue
    }
    return nil
}

func expectedValueMatches(_ expected: Any, _ actual: Any?) -> Bool {
    if let expectedBool = expected as? Bool {
        return (actual as? Bool) == expectedBool
    }
    if let expectedNumber = numericValue(expected) {
        guard let actualNumber = numericValue(actual) else {
            return false
        }
        return abs(actualNumber - expectedNumber) < 0.001
    }
    if let expectedString = expected as? String {
        return (actual as? String) == expectedString
    }
    return false
}

func deleteStateMatches(_ asset: PHAsset, expected: [String: Any]) -> Bool {
    let current = deleteStatePayload(asset)
    for (key, value) in expected {
        if !expectedValueMatches(value, current[key]) {
            return false
        }
    }
    return true
}

func albumStateMatches(_ album: PHAssetCollection, expected: [String: Any]) -> Bool {
    let current = albumStatePayload(album)
    for (key, value) in expected {
        if !expectedValueMatches(value, current[key]) {
            return false
        }
    }
    return true
}

let input: Data
if let inputJSONFilePath {
    input = (try? Data(contentsOf: URL(fileURLWithPath: inputJSONFilePath))) ?? Data()
} else {
    input = FileHandle.standardInput.readDataToEndOfFile()
}
guard
    let object = try? JSONSerialization.jsonObject(with: input, options: []),
    let request = object as? [String: Any]
else {
    emit([
        "schema_version": 1,
        "status": "error",
        "source": "photos",
        "warnings": [warning("invalid_request", "Expected JSON request.")],
    ])
}

let command = stringValue(request, "command")

if command == "request_photos_full_access" {
    requestPhotosFullAccess()
}

if command == "photos" {
    ensureAccess()
    let query = stringValue(request, "query").lowercased()
    let mediaType = stringValue(request, "media_type").lowercased()
    let limit = max(1, min(intValue(request, "limit", 20), 10000))
    let maxAssets = max(1, min(intValue(request, "max_assets", 5000), 10000))
    let options = PHFetchOptions()
    options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
    let fetched = PHAsset.fetchAssets(with: options)

    var scanned = 0
    var scanTruncated = false
    var results: [[String: Any]] = []
    fetched.enumerateObjects { asset, _, stop in
        if scanned >= maxAssets {
            scanTruncated = true
            stop.pointee = true
            return
        }
        scanned += 1
        if !matches(asset, query: query, mediaType: mediaType) {
            return
        }
        results.append(assetPayload(asset, includeResources: false))
        if results.count >= limit {
            stop.pointee = true
        }
    }

    var warnings: [[String: String]] = []
    if scanTruncated {
        warnings.append(warning("scan_truncated", "Photos scan stopped at the scan limit."))
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "authorization_status": authorizationName(authorizationStatus()),
        "assets": results,
        "scanned": scanned,
        "warnings": warnings,
    ])
}

if command == "photo_by_id" {
    ensureAccess()
    let assetId = stringValue(request, "asset_id")
    if assetId.isEmpty {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "asset": NSNull(),
            "warnings": [warning("invalid_asset_id", "Expected Photos asset identifier.")],
        ])
    }
    let fetched = PHAsset.fetchAssets(withLocalIdentifiers: [assetId], options: nil)
    guard let asset = fetched.firstObject else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "photos",
            "asset": NSNull(),
            "warnings": [],
        ])
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "asset": assetPayload(asset, includeResources: true),
        "warnings": [],
    ])
}

if command == "export_photo_by_id" {
    ensureAccess()
    let assetId = stringValue(request, "asset_id")
    let outputDirValue = (stringValue(request, "output_dir") as NSString).expandingTildeInPath
    if assetId.isEmpty || outputDirValue.isEmpty {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "asset": NSNull(),
            "warnings": [warning("invalid_export_request", "Expected Photos asset identifier and output directory.")],
        ])
    }
    let fetched = PHAsset.fetchAssets(withLocalIdentifiers: [assetId], options: nil)
    guard let asset = fetched.firstObject else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "photos",
            "asset": NSNull(),
            "warnings": [],
        ])
    }
    guard let resource = resources(asset).first else {
        emit([
            "schema_version": 1,
            "status": "export_unavailable",
            "source": "photos",
            "asset": assetPayload(asset, includeResources: true),
            "warnings": [warning("photos_resource_unavailable", "Photos asset has no exportable local resource.")],
        ])
    }

    let manager = FileManager.default
    let outputDir = URL(fileURLWithPath: outputDirValue, isDirectory: true)
    do {
        try manager.createDirectory(at: outputDir, withIntermediateDirectories: true)
    } catch {
        emit([
            "schema_version": 1,
            "status": "export_unavailable",
            "source": "photos",
            "asset": assetPayload(asset, includeResources: true),
            "warnings": [warning("invalid_output_dir", "Photos export output directory is unavailable.")],
        ])
    }

    let outputName = sanitizedFilename(
        stringValue(request, "filename"),
        fallback: resource.originalFilename
    )
    let outputURL: URL
    do {
        outputURL = try uniqueOutputURL(directory: outputDir, filename: outputName)
    } catch {
        emit([
            "schema_version": 1,
            "status": "export_unavailable",
            "source": "photos",
            "asset": assetPayload(asset, includeResources: true),
            "warnings": [warning("photos_export_name_unavailable", "Photos export filename could not be allocated.")],
        ])
    }

    let options = PHAssetResourceRequestOptions()
    options.isNetworkAccessAllowed = false
    let semaphore = DispatchSemaphore(value: 0)
    var exportWarning: [String: String]? = nil
    PHAssetResourceManager.default().writeData(for: resource, toFile: outputURL, options: options) { error in
        if error != nil {
            exportWarning = warning("photos_export_failed", "Photos asset could not be exported from local PhotoKit data.")
        }
        semaphore.signal()
    }

    if semaphore.wait(timeout: .now() + 30) == .timedOut {
        emit([
            "schema_version": 1,
            "status": "export_unavailable",
            "source": "photos",
            "asset": assetPayload(asset, includeResources: true),
            "warnings": [warning("photos_export_timeout", "Photos asset export timed out.")],
        ])
    }
    if let exportWarning = exportWarning {
        emit([
            "schema_version": 1,
            "status": "export_unavailable",
            "source": "photos",
            "asset": assetPayload(asset, includeResources: true),
            "warnings": [exportWarning],
        ])
    }

    var payload = assetPayload(asset, includeResources: true)
    let attributes = try? manager.attributesOfItem(atPath: outputURL.path)
    payload["asset_content_exported"] = true
    payload["exported_path"] = outputURL.path
    payload["exported_filename"] = outputURL.lastPathComponent
    payload["exported_bytes"] = (attributes?[.size] as? NSNumber)?.intValue ?? 0
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "asset": payload,
        "warnings": [],
    ])
}

if command == "photo_albums" {
    ensureAccess()
    let query = stringValue(request, "query").lowercased()
    let limit = max(1, min(intValue(request, "limit", 20), 10000))
    let maxAlbums = max(1, min(intValue(request, "max_albums", 5000), 10000))
    let fetched = PHAssetCollection.fetchAssetCollections(with: .album, subtype: .albumRegular, options: nil)

    var scanned = 0
    var scanTruncated = false
    var resultTruncated = false
    var results: [[String: Any]] = []
    fetched.enumerateObjects { album, _, stop in
        if scanned >= maxAlbums {
            scanTruncated = true
            stop.pointee = true
            return
        }
        scanned += 1
        if !albumMatches(album, query: query) {
            return
        }
        results.append(albumPayload(album))
        if results.count >= limit {
            resultTruncated = true
            stop.pointee = true
        }
    }

    var warnings: [[String: String]] = []
    if scanTruncated {
        warnings.append(warning("scan_truncated", "Photos album scan stopped at the scan limit."))
    }
    if resultTruncated {
        warnings.append(warning("result_truncated", "Photos album search stopped at the result limit."))
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "authorization_status": authorizationName(authorizationStatus()),
        "albums": results,
        "scanned": scanned,
        "warnings": warnings,
    ])
}

if command == "photo_album_by_id" {
    ensureAccess()
    let albumId = stringValue(request, "album_id")
    if albumId.isEmpty {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(authorizationStatus()),
            "album": NSNull(),
            "warnings": [warning("invalid_album_id", "Expected Photos album identifier.")],
        ])
    }
    guard let album = fetchAlbumById(albumId) else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "photos",
            "authorization_status": authorizationName(authorizationStatus()),
            "album": NSNull(),
            "warnings": [],
        ])
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "authorization_status": authorizationName(authorizationStatus()),
        "album": albumPayload(album),
        "warnings": [],
    ])
}

if command == "photo_album_assets" {
    ensureAccess()
    let albumId = stringValue(request, "album_id")
    let limit = max(1, min(intValue(request, "limit", 20), 50))
    let maxAssets = max(1, min(intValue(request, "max_assets", 5000), 10000))
    if albumId.isEmpty {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(authorizationStatus()),
            "album": NSNull(),
            "assets": [],
            "warnings": [warning("invalid_album_id", "Expected Photos album identifier.")],
        ])
    }
    guard let album = fetchAlbumById(albumId) else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "photos",
            "authorization_status": authorizationName(authorizationStatus()),
            "album": NSNull(),
            "assets": [],
            "warnings": [],
        ])
    }

    let fetched = albumAssets(album)
    var results: [[String: Any]] = []
    let fetchCount = fetched.count
    let scanCount = min(fetchCount, maxAssets)
    if scanCount > 0 {
        for index in 0..<scanCount {
            results.append(assetPayload(fetched.object(at: index), includeResources: false))
            if results.count >= limit {
                break
            }
        }
    }

    var warnings: [[String: String]] = []
    if fetchCount > maxAssets {
        warnings.append(warning("scan_truncated", "Photos album asset scan stopped at the scan limit."))
    }
    if fetchCount > results.count {
        warnings.append(warning("result_truncated", "Photos album asset listing stopped at the result limit."))
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "authorization_status": authorizationName(authorizationStatus()),
        "album": albumPayload(album),
        "assets": results,
        "asset_count": fetchCount,
        "scanned": scanCount,
        "warnings": warnings,
    ])
}

if command == "photo_album_membership" {
    ensureAccess()
    let assetId = stringValue(request, "asset_id")
    let albumId = stringValue(request, "album_id")
    let assetFetch = PHAsset.fetchAssets(withLocalIdentifiers: [assetId], options: nil)
    guard let asset = assetFetch.firstObject, let album = fetchAlbumById(albumId) else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "photos",
            "authorization_status": authorizationName(authorizationStatus()),
            "asset": NSNull(),
            "album": NSNull(),
            "in_album": false,
            "warnings": [],
        ])
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "authorization_status": authorizationName(authorizationStatus()),
        "asset": assetPayload(asset, includeResources: true),
        "album": albumPayload(album),
        "in_album": albumContainsAsset(album, assetId: asset.localIdentifier),
        "warnings": [],
    ])
}

if command == "photos_album_management" {
    let status = authorizationStatus()
    if !fullLibraryAuthorized(status) {
        emit(albumManagementAccessUnavailablePayload(status))
    }

    let operation = stringValue(request, "operation")
    let albumId = stringValue(request, "album_id")
    let albumTitle = stringValue(request, "album_title")
    let expectedAlbumState = request["expected_album_state"] as? [String: Any]
    if operation == "create_album" {
        if !isValidAlbumTitle(albumTitle) {
            emit([
                "schema_version": 1,
                "status": "error",
                "source": "photos",
                "authorization_status": authorizationName(status),
                "album": NSNull(),
                "warnings": [warning("invalid_album_title", "Photos album title must be non-empty and 200 characters or fewer.")],
            ])
        }
        if fetchAlbumWithExactTitle(albumTitle) != nil {
            emit([
                "schema_version": 1,
                "status": "error",
                "source": "photos",
                "authorization_status": authorizationName(status),
                "album": NSNull(),
                "warnings": [warning("duplicate_album_title", "A Photos album with the requested title already exists.")],
            ])
        }
        let semaphore = DispatchSemaphore(value: 0)
        var createdAlbumId = ""
        var applyWarning: [String: String]? = nil
        PHPhotoLibrary.shared().performChanges({
            let changeRequest = PHAssetCollectionChangeRequest.creationRequestForAssetCollection(withTitle: albumTitle)
            createdAlbumId = changeRequest.placeholderForCreatedAssetCollection.localIdentifier
        }, completionHandler: { success, error in
            if !success {
                applyWarning = warning("photos_album_management_failed", "Photos album could not be created.")
            }
            semaphore.signal()
        })
        if semaphore.wait(timeout: .now() + 60) == .timedOut {
            emit([
                "schema_version": 1,
                "status": "apply_unknown",
                "source": "photos",
                "authorization_status": authorizationName(status),
                "album": NSNull(),
                "warnings": [warning("photos_apply_timeout", "Photos album management timed out.")],
            ])
        }
        if let applyWarning = applyWarning {
            emit([
                "schema_version": 1,
                "status": "error",
                "source": "photos",
                "authorization_status": authorizationName(status),
                "album": NSNull(),
                "warnings": [applyWarning],
            ])
        }
        guard let album = fetchAlbumById(createdAlbumId), (album.localizedTitle ?? "") == albumTitle else {
            emit([
                "schema_version": 1,
                "status": "apply_unknown",
                "source": "photos",
                "authorization_status": authorizationName(status),
                "album": NSNull(),
                "warnings": [warning("read_back_unavailable", "Photos album management read-back was unavailable.")],
            ])
        }
        if fetchAlbumWithExactTitle(albumTitle, excludingAlbumId: createdAlbumId) != nil {
            emit([
                "schema_version": 1,
                "status": "apply_unknown",
                "source": "photos",
                "authorization_status": authorizationName(status),
                "album": albumPayload(album),
                "mutation_applied": true,
                "raw_album_identifier_returned": false,
                "warnings": [warning("duplicate_album_title", "Photos album title uniqueness was not preserved after apply.")],
            ])
        }
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "album": albumPayload(album),
            "mutation_applied": true,
            "raw_album_identifier_returned": false,
            "warnings": [],
        ])
    }

    guard
        let expectedAlbumState = expectedAlbumState,
        (operation == "rename_album" || operation == "delete_album"),
        !albumId.isEmpty,
        let album = fetchAlbumById(albumId)
    else {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "album": NSNull(),
            "warnings": [warning("invalid_album_management_request", "Expected Photos album management operation, album, and expected state.")],
        ])
    }
    if !albumStateMatches(album, expected: expectedAlbumState) {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "album": albumPayload(album),
            "warnings": [warning("expected_state_mismatch", "Current Photos album state did not match expected state.")],
        ])
    }
    if operation == "rename_album" && !isValidAlbumTitle(albumTitle) {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "album": albumPayload(album),
            "warnings": [warning("invalid_album_title", "Photos album title must be non-empty and 200 characters or fewer.")],
        ])
    }
    if operation == "rename_album" && !album.canPerform(.rename) {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "album": albumPayload(album),
            "warnings": [warning("photos_album_rename_not_supported", "Selected Photos album does not allow renaming.")],
        ])
    }
    if operation == "rename_album" && fetchAlbumWithExactTitle(albumTitle, excludingAlbumId: albumId) != nil {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "album": albumPayload(album),
            "warnings": [warning("duplicate_album_title", "A Photos album with the requested title already exists.")],
        ])
    }
    if operation == "delete_album" && !album.canPerform(.delete) {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "album": albumPayload(album),
            "warnings": [warning("photos_album_delete_not_supported", "Selected Photos album does not allow deletion.")],
        ])
    }
    if operation == "delete_album" && albumAssetCount(album) != 0 {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "album": albumPayload(album),
            "warnings": [warning("non_empty_album_blocked", "Photos album delete is limited to empty regular albums.")],
        ])
    }

    let semaphore = DispatchSemaphore(value: 0)
    var applyWarning: [String: String]? = nil
    PHPhotoLibrary.shared().performChanges({
        if operation == "rename_album" {
            guard let changeRequest = PHAssetCollectionChangeRequest(for: album) else {
                applyWarning = warning("photos_album_management_failed", "Photos album change request could not be created.")
                return
            }
            changeRequest.title = albumTitle
        } else {
            PHAssetCollectionChangeRequest.deleteAssetCollections([album] as NSArray)
        }
    }, completionHandler: { success, error in
        if !success && applyWarning == nil {
            applyWarning = warning("photos_album_management_failed", "Photos album could not be changed.")
        }
        semaphore.signal()
    })
    if semaphore.wait(timeout: .now() + 60) == .timedOut {
        emit([
            "schema_version": 1,
            "status": "apply_unknown",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "album": NSNull(),
            "warnings": [warning("photos_apply_timeout", "Photos album management timed out.")],
        ])
    }
    if let applyWarning = applyWarning {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "album": NSNull(),
            "warnings": [applyWarning],
        ])
    }

    if operation == "delete_album" {
        let deleted = fetchAlbumById(albumId) == nil
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "album": NSNull(),
            "deleted": deleted,
            "verified_absent": deleted,
            "mutation_applied": true,
            "raw_album_identifier_returned": false,
            "warnings": [],
        ])
    }
    guard let readBackAlbum = fetchAlbumById(albumId), (readBackAlbum.localizedTitle ?? "") == albumTitle else {
        emit([
            "schema_version": 1,
            "status": "apply_unknown",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "album": NSNull(),
            "warnings": [warning("read_back_unavailable", "Photos album management read-back was unavailable.")],
        ])
    }
    if fetchAlbumWithExactTitle(albumTitle, excludingAlbumId: albumId) != nil {
        emit([
            "schema_version": 1,
            "status": "apply_unknown",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "album": albumPayload(readBackAlbum),
            "mutation_applied": true,
            "raw_album_identifier_returned": false,
            "warnings": [warning("duplicate_album_title", "Photos album title uniqueness was not preserved after apply.")],
        ])
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "authorization_status": authorizationName(status),
        "album": albumPayload(readBackAlbum),
        "mutation_applied": true,
        "raw_album_identifier_returned": false,
        "warnings": [],
    ])
}

if command == "photos_album_membership" {
    let status = authorizationStatus()
    if !readAuthorized(status) {
        emit(applyAccessUnavailablePayload())
    }

    let operation = stringValue(request, "operation")
    let assetId = stringValue(request, "asset_id")
    let albumId = stringValue(request, "album_id")
    guard
        let expectedAssetState = request["expected_asset_state"] as? [String: Any],
        let expectedAlbumState = request["expected_album_state"] as? [String: Any],
        let expectedInAlbum = request["expected_in_album"] as? Bool,
        (operation == "add_to_album" || operation == "remove_from_album"),
        !assetId.isEmpty,
        !albumId.isEmpty
    else {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "album": NSNull(),
            "in_album": false,
            "warnings": [warning("invalid_album_membership_request", "Expected Photos asset, album, operation, and expected membership state.")],
        ])
    }

    let assetFetch = PHAsset.fetchAssets(withLocalIdentifiers: [assetId], options: nil)
    guard let asset = assetFetch.firstObject, let album = fetchAlbumById(albumId) else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "album": NSNull(),
            "in_album": false,
            "warnings": [],
        ])
    }
    if !deleteStateMatches(asset, expected: expectedAssetState) || !albumStateMatches(album, expected: expectedAlbumState) {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "album": NSNull(),
            "in_album": albumContainsAsset(album, assetId: asset.localIdentifier),
            "warnings": [warning("expected_state_mismatch", "Current Photos asset or album state did not match expected state.")],
        ])
    }

    let currentAssets = albumAssets(album)
    let currentlyInAlbum = albumContainsAsset(album, assetId: asset.localIdentifier)
    if currentlyInAlbum != expectedInAlbum {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "album": albumPayload(album),
            "in_album": currentlyInAlbum,
            "warnings": [warning("expected_membership_mismatch", "Current Photos album membership did not match expected state.")],
        ])
    }
    if operation == "add_to_album" && !album.canPerform(.addContent) {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "album": albumPayload(album),
            "in_album": currentlyInAlbum,
            "warnings": [warning("photos_album_add_not_supported", "Selected Photos album does not allow adding assets.")],
        ])
    }
    if operation == "remove_from_album" && !album.canPerform(.removeContent) {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "album": albumPayload(album),
            "in_album": currentlyInAlbum,
            "warnings": [warning("photos_album_remove_not_supported", "Selected Photos album does not allow removing assets.")],
        ])
    }

    let semaphore = DispatchSemaphore(value: 0)
    var applyWarning: [String: String]? = nil

    PHPhotoLibrary.shared().performChanges({
        guard let changeRequest = PHAssetCollectionChangeRequest(for: album, assets: currentAssets) else {
            applyWarning = warning("photos_album_membership_failed", "Photos album membership change request could not be created.")
            return
        }
        if operation == "add_to_album" {
            changeRequest.addAssets([asset] as NSArray)
        } else {
            changeRequest.removeAssets([asset] as NSArray)
        }
    }, completionHandler: { success, error in
        if !success && applyWarning == nil {
            applyWarning = warning("photos_album_membership_failed", "Photos album membership could not be changed.")
        }
        semaphore.signal()
    })

    if semaphore.wait(timeout: .now() + 60) == .timedOut {
        emit([
            "schema_version": 1,
            "status": "apply_unknown",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "album": NSNull(),
            "in_album": currentlyInAlbum,
            "warnings": [warning("photos_apply_timeout", "Photos album membership change timed out.")],
        ])
    }
    if let applyWarning = applyWarning {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "album": NSNull(),
            "in_album": currentlyInAlbum,
            "warnings": [applyWarning],
        ])
    }

    let readBackAssetFetch = PHAsset.fetchAssets(withLocalIdentifiers: [assetId], options: nil)
    guard let readBackAsset = readBackAssetFetch.firstObject, let readBackAlbum = fetchAlbumById(albumId) else {
        emit([
            "schema_version": 1,
            "status": "apply_unknown",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "album": NSNull(),
            "in_album": false,
            "warnings": [warning("read_back_unavailable", "Photos album membership read-back was unavailable.")],
        ])
    }
    let readBackMembership = albumContainsAsset(readBackAlbum, assetId: readBackAsset.localIdentifier)
    let targetMembership = operation == "add_to_album"
    if readBackMembership != targetMembership {
        emit([
            "schema_version": 1,
            "status": "apply_unknown",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": assetPayload(readBackAsset, includeResources: true),
            "album": albumPayload(readBackAlbum),
            "in_album": readBackMembership,
            "warnings": [warning("read_back_state_mismatch", "Photos album membership read-back did not match target state.")],
        ])
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "authorization_status": authorizationName(status),
        "asset": assetPayload(readBackAsset, includeResources: true),
        "album": albumPayload(readBackAlbum),
        "in_album": readBackMembership,
        "mutation_applied": true,
        "asset_content_returned": false,
        "raw_asset_identifier_returned": false,
        "raw_album_identifier_returned": false,
        "warnings": [],
    ])
}

if command == "photos_apply_change" {
    let status = authorizationStatus()
    if !readAuthorized(status) {
        emit(applyAccessUnavailablePayload())
    }

    let operation = stringValue(request, "operation")
    let mediaType = stringValue(request, "media_type")
    let sourcePath = (stringValue(request, "source_file") as NSString).expandingTildeInPath
    if operation != "import" || sourcePath.isEmpty || !(mediaType == "image" || mediaType == "video") {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "asset": NSNull(),
            "warnings": [warning("invalid_import_request", "Expected Photos import operation, media type, and source file.")],
        ])
    }

    var isDirectory = ObjCBool(false)
    guard FileManager.default.fileExists(atPath: sourcePath, isDirectory: &isDirectory), !isDirectory.boolValue else {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "asset": NSNull(),
            "warnings": [warning("source_file_unavailable", "Photos import source file is unavailable.")],
        ])
    }

    let sourceURL = URL(fileURLWithPath: sourcePath, isDirectory: false)
    let semaphore = DispatchSemaphore(value: 0)
    var createdAssetIdentifier = ""
    var applyWarning: [String: String]? = nil

    PHPhotoLibrary.shared().performChanges({
        if mediaType == "image" {
            guard let changeRequest = PHAssetChangeRequest.creationRequestForAssetFromImage(atFileURL: sourceURL) else {
                applyWarning = warning("photos_import_failed", "Photos image import request could not be created.")
                return
            }
            createdAssetIdentifier = changeRequest.placeholderForCreatedAsset?.localIdentifier ?? ""
        } else {
            guard let changeRequest = PHAssetChangeRequest.creationRequestForAssetFromVideo(atFileURL: sourceURL) else {
                applyWarning = warning("photos_import_failed", "Photos video import request could not be created.")
                return
            }
            createdAssetIdentifier = changeRequest.placeholderForCreatedAsset?.localIdentifier ?? ""
        }
    }, completionHandler: { success, error in
        if !success && applyWarning == nil {
            applyWarning = warning("photos_import_failed", "Photos asset could not be imported from the selected local file.")
        }
        semaphore.signal()
    })

    if semaphore.wait(timeout: .now() + 60) == .timedOut {
        emit([
            "schema_version": 1,
            "status": "apply_unknown",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "warnings": [warning("photos_import_timeout", "Photos import timed out.")],
        ])
    }
    if let applyWarning = applyWarning {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "warnings": [applyWarning],
        ])
    }
    if createdAssetIdentifier.isEmpty {
        emit([
            "schema_version": 1,
            "status": "apply_unknown",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "warnings": [warning("read_back_unavailable", "Photos import completed without a readable asset placeholder.")],
        ])
    }

    let fetched = PHAsset.fetchAssets(withLocalIdentifiers: [createdAssetIdentifier], options: nil)
    guard let asset = fetched.firstObject else {
        emit([
            "schema_version": 1,
            "status": "apply_unknown",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "warnings": [warning("read_back_unavailable", "Photos import completed but the created asset could not be read back.")],
        ])
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "authorization_status": authorizationName(status),
        "asset": assetPayload(asset, includeResources: true),
        "warnings": [],
    ])
}

if command == "photos_update_flags" {
    let status = authorizationStatus()
    if !readAuthorized(status) {
        emit(applyAccessUnavailablePayload())
    }

    let assetId = stringValue(request, "asset_id")
    guard
        let expectedFavorite = request["expected_favorite"] as? Bool,
        let expectedHidden = request["expected_hidden"] as? Bool,
        let targetFavorite = request["favorite"] as? Bool,
        let targetHidden = request["hidden"] as? Bool,
        !assetId.isEmpty
    else {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "asset": NSNull(),
            "warnings": [warning("invalid_update_request", "Expected Photos asset identifier and favorite/hidden flags.")],
        ])
    }

    let fetched = PHAsset.fetchAssets(withLocalIdentifiers: [assetId], options: nil)
    guard let asset = fetched.firstObject else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "warnings": [],
        ])
    }
    if asset.isFavorite != expectedFavorite || asset.isHidden != expectedHidden {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "warnings": [warning("expected_state_mismatch", "Current Photos asset favorite/hidden state did not match expected state.")],
        ])
    }
    if #available(macOS 10.15, *) {
        if !asset.canPerform(.properties) {
            emit([
                "schema_version": 1,
                "status": "error",
                "source": "photos",
                "authorization_status": authorizationName(status),
                "asset": NSNull(),
                "warnings": [warning("photos_update_not_supported", "Photos asset does not allow property updates.")],
            ])
        }
    }

    let semaphore = DispatchSemaphore(value: 0)
    var applyWarning: [String: String]? = nil

    PHPhotoLibrary.shared().performChanges({
        let changeRequest = PHAssetChangeRequest(for: asset)
        changeRequest.isFavorite = targetFavorite
        changeRequest.isHidden = targetHidden
    }, completionHandler: { success, error in
        if !success {
            applyWarning = warning("photos_update_failed", "Photos asset flags could not be updated.")
        }
        semaphore.signal()
    })

    if semaphore.wait(timeout: .now() + 60) == .timedOut {
        emit([
            "schema_version": 1,
            "status": "apply_unknown",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "warnings": [warning("photos_apply_timeout", "Photos update timed out.")],
        ])
    }
    if let applyWarning = applyWarning {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "warnings": [applyWarning],
        ])
    }

    let readBack = PHAsset.fetchAssets(withLocalIdentifiers: [assetId], options: nil)
    guard let updatedAsset = readBack.firstObject else {
        emit([
            "schema_version": 1,
            "status": "apply_unknown",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "warnings": [warning("read_back_unavailable", "Photos update completed but the selected asset could not be read back.")],
        ])
    }
    if updatedAsset.isFavorite != targetFavorite || updatedAsset.isHidden != targetHidden {
        emit([
            "schema_version": 1,
            "status": "apply_unknown",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "warnings": [warning("read_back_state_mismatch", "Photos update read-back did not match the approved target state.")],
        ])
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "authorization_status": authorizationName(status),
        "asset": assetPayload(updatedAsset, includeResources: true),
        "warnings": [],
    ])
}

if command == "photos_delete_asset" {
    let status = authorizationStatus()
    if !readAuthorized(status) {
        emit(applyAccessUnavailablePayload())
    }

    let assetId = stringValue(request, "asset_id")
    guard
        let expectedState = request["expected_state"] as? [String: Any],
        !assetId.isEmpty,
        !expectedState.isEmpty
    else {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "deleted": false,
            "verified_absent": false,
            "warnings": [warning("invalid_delete_request", "Expected Photos asset identifier and delete state.")],
        ])
    }

    let fetched = PHAsset.fetchAssets(withLocalIdentifiers: [assetId], options: nil)
    guard let asset = fetched.firstObject else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "deleted": false,
            "verified_absent": true,
            "warnings": [],
        ])
    }
    if !deleteStateMatches(asset, expected: expectedState) {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "deleted": false,
            "verified_absent": false,
            "warnings": [warning("expected_state_mismatch", "Current Photos asset state did not match expected delete state.")],
        ])
    }
    if #available(macOS 10.15, *) {
        if !asset.canPerform(.delete) {
            emit([
                "schema_version": 1,
                "status": "error",
                "source": "photos",
                "authorization_status": authorizationName(status),
                "asset": NSNull(),
                "deleted": false,
                "verified_absent": false,
                "warnings": [warning("photos_delete_not_supported", "Photos asset does not allow deletion.")],
            ])
        }
    }

    let semaphore = DispatchSemaphore(value: 0)
    var applyWarning: [String: String]? = nil

    PHPhotoLibrary.shared().performChanges({
        PHAssetChangeRequest.deleteAssets([asset] as NSArray)
    }, completionHandler: { success, error in
        if !success {
            applyWarning = warning("photos_delete_failed", "Photos asset could not be deleted.")
        }
        semaphore.signal()
    })

    if semaphore.wait(timeout: .now() + 60) == .timedOut {
        emit([
            "schema_version": 1,
            "status": "apply_unknown",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "deleted": false,
            "verified_absent": false,
            "warnings": [warning("photos_apply_timeout", "Photos delete timed out.")],
        ])
    }
    if let applyWarning = applyWarning {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "deleted": false,
            "verified_absent": false,
            "warnings": [applyWarning],
        ])
    }

    let readBack = PHAsset.fetchAssets(withLocalIdentifiers: [assetId], options: nil)
    if readBack.firstObject != nil {
        emit([
            "schema_version": 1,
            "status": "apply_unknown",
            "source": "photos",
            "authorization_status": authorizationName(status),
            "asset": NSNull(),
            "deleted": true,
            "verified_absent": false,
            "warnings": [warning("read_back_state_mismatch", "Photos delete read-back did not prove absence.")],
        ])
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "photos",
        "authorization_status": authorizationName(status),
        "asset": NSNull(),
        "mutation_applied": true,
        "deleted": true,
        "verified_absent": true,
        "asset_content_returned": false,
        "raw_asset_identifier_returned": false,
        "recently_deleted_empty": false,
        "warnings": [],
    ])
}

emit([
    "schema_version": 1,
    "status": "error",
    "source": "photos",
    "warnings": [warning("unknown_command", "Unsupported Photos helper command.")],
])
