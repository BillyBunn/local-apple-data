import Foundation

struct DecodeItem: Decodable {
    let id: String
    let base64: String
}

struct DecodeRequest: Decodable {
    let mode: String
    let items: [DecodeItem]?
    let maxChars: Int?
}

func emit(_ payload: [String: Any]) {
    let data = try! JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
}

let input = FileHandle.standardInput.readDataToEndOfFile()

guard
    let request = try? JSONDecoder().decode(DecodeRequest.self, from: input),
    request.mode == "decode_attributed_bodies"
else {
    emit([
        "results": [],
        "source": "messages_helper",
        "status": "error",
        "warnings": [["code": "invalid_request", "message": "Messages helper request was invalid."]],
    ])
    exit(0)
}

let maxChars = max(1, min(request.maxChars ?? 2000, 12000))
var results: [[String: Any]] = []

for item in request.items ?? [] {
    guard let data = Data(base64Encoded: item.base64) else {
        results.append(["id": item.id, "status": "unavailable", "text": ""])
        continue
    }

    let object = NSUnarchiver.unarchiveObject(with: data)
    let rawText: String
    if let attributed = object as? NSAttributedString {
        rawText = attributed.string
    } else if let string = object as? String {
        rawText = string
    } else {
        rawText = ""
    }

    let text = String(rawText.prefix(maxChars))
    results.append(["id": item.id, "status": text.isEmpty ? "unavailable" : "ok", "text": text])
}

emit([
    "results": results,
    "source": "messages_helper",
    "status": "ok",
    "warnings": [],
])
