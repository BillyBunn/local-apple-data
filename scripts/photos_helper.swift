import Foundation
import Photos

let isoFormatter = ISO8601DateFormatter()
isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

func emit(_ payload: [String: Any]) -> Never {
    let data = try! JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
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

let input = FileHandle.standardInput.readDataToEndOfFile()
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

emit([
    "schema_version": 1,
    "status": "error",
    "source": "photos",
    "warnings": [warning("unknown_command", "Unsupported Photos helper command.")],
])
