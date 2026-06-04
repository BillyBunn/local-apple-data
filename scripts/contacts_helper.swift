import Contacts
import Foundation

let isoFormatter = ISO8601DateFormatter()
isoFormatter.formatOptions = [.withFullDate]

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

func authorizationName(_ status: CNAuthorizationStatus) -> String {
    switch status {
    case .authorized:
        return "authorized"
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

func ensureAccess() -> CNContactStore? {
    let status = CNContactStore.authorizationStatus(for: .contacts)
    if status != .authorized {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "authorization_status": authorizationName(status),
            "contacts": [],
            "contact": NSNull(),
            "warnings": [
                warning(
                    "contacts_access_unavailable",
                    "Contacts access is not authorized for this process."
                )
            ],
        ])
    }
    return CNContactStore()
}

let baseKeys: [CNKeyDescriptor] = [
    CNContactIdentifierKey as CNKeyDescriptor,
    CNContactTypeKey as CNKeyDescriptor,
    CNContactNamePrefixKey as CNKeyDescriptor,
    CNContactGivenNameKey as CNKeyDescriptor,
    CNContactMiddleNameKey as CNKeyDescriptor,
    CNContactFamilyNameKey as CNKeyDescriptor,
    CNContactPreviousFamilyNameKey as CNKeyDescriptor,
    CNContactNameSuffixKey as CNKeyDescriptor,
    CNContactNicknameKey as CNKeyDescriptor,
    CNContactOrganizationNameKey as CNKeyDescriptor,
    CNContactDepartmentNameKey as CNKeyDescriptor,
    CNContactJobTitleKey as CNKeyDescriptor,
    CNContactEmailAddressesKey as CNKeyDescriptor,
    CNContactPhoneNumbersKey as CNKeyDescriptor,
    CNContactPostalAddressesKey as CNKeyDescriptor,
    CNContactUrlAddressesKey as CNKeyDescriptor,
    CNContactBirthdayKey as CNKeyDescriptor,
    CNContactDatesKey as CNKeyDescriptor,
    CNContactSocialProfilesKey as CNKeyDescriptor,
    CNContactInstantMessageAddressesKey as CNKeyDescriptor,
    CNContactRelationsKey as CNKeyDescriptor,
    CNContactImageDataAvailableKey as CNKeyDescriptor,
]

func labelName(_ label: String?) -> String {
    guard let label = label else {
        return ""
    }
    return CNLabeledValue<NSString>.localizedString(forLabel: label)
}

func displayName(_ contact: CNContact) -> String {
    if let name = CNContactFormatter.string(from: contact, style: .fullName),
       !name.isEmpty {
        return name
    }
    if !contact.organizationName.isEmpty {
        return contact.organizationName
    }
    return [contact.givenName, contact.familyName]
        .filter { !$0.isEmpty }
        .joined(separator: " ")
}

func contactTypeName(_ contact: CNContact) -> String {
    switch contact.contactType {
    case .person:
        return "person"
    case .organization:
        return "organization"
    @unknown default:
        return "unknown"
    }
}

func dateComponentsPayload(_ components: DateComponents?) -> [String: Any] {
    guard let components = components else {
        return [:]
    }
    var payload: [String: Any] = [:]
    if let year = components.year {
        payload["year"] = year
    }
    if let month = components.month {
        payload["month"] = month
    }
    if let day = components.day {
        payload["day"] = day
    }
    return payload
}

func stringLabeledValues(_ values: [CNLabeledValue<NSString>]) -> [[String: Any]] {
    return values.map {
        [
            "label": labelName($0.label),
            "value": String($0.value),
        ]
    }
}

func phonePayloads(_ values: [CNLabeledValue<CNPhoneNumber>]) -> [[String: Any]] {
    return values.map {
        [
            "label": labelName($0.label),
            "value": $0.value.stringValue,
        ]
    }
}

func postalPayloads(_ values: [CNLabeledValue<CNPostalAddress>]) -> [[String: Any]] {
    return values.map {
        let address = $0.value
        return [
            "label": labelName($0.label),
            "street": address.street,
            "city": address.city,
            "state": address.state,
            "postal_code": address.postalCode,
            "country": address.country,
            "iso_country_code": address.isoCountryCode,
        ]
    }
}

func datedPayloads(_ values: [CNLabeledValue<NSDateComponents>]) -> [[String: Any]] {
    return values.map {
        [
            "label": labelName($0.label),
            "date": dateComponentsPayload($0.value as DateComponents),
        ]
    }
}

func socialPayloads(_ values: [CNLabeledValue<CNSocialProfile>]) -> [[String: Any]] {
    return values.map {
        let profile = $0.value
        return [
            "label": labelName($0.label),
            "service": profile.service,
            "username": profile.username,
            "url": profile.urlString,
        ]
    }
}

func instantMessagePayloads(_ values: [CNLabeledValue<CNInstantMessageAddress>]) -> [[String: Any]] {
    return values.map {
        let address = $0.value
        return [
            "label": labelName($0.label),
            "service": address.service,
            "username": address.username,
        ]
    }
}

func relationPayloads(_ values: [CNLabeledValue<CNContactRelation>]) -> [[String: Any]] {
    return values.map {
        [
            "label": labelName($0.label),
            "name": $0.value.name,
        ]
    }
}

func contactPayload(_ contact: CNContact, includeDetails: Bool) -> [String: Any] {
    var payload: [String: Any] = [
        "contact_id": contact.identifier,
        "display_name": displayName(contact),
        "contact_type": contactTypeName(contact),
        "given_name": contact.givenName,
        "family_name": contact.familyName,
        "nickname": contact.nickname,
        "organization_name": contact.organizationName,
        "department_name": contact.departmentName,
        "job_title": contact.jobTitle,
        "email_count": contact.emailAddresses.count,
        "phone_count": contact.phoneNumbers.count,
        "postal_address_count": contact.postalAddresses.count,
        "url_count": contact.urlAddresses.count,
        "social_profile_count": contact.socialProfiles.count,
        "instant_message_count": contact.instantMessageAddresses.count,
        "relation_count": contact.contactRelations.count,
        "dates_count": contact.dates.count,
        "birthday_present": contact.birthday != nil,
        "image_available": contact.imageDataAvailable,
        "note_status": "requires_entitlement",
    ]
    if includeDetails {
        payload["name_prefix"] = contact.namePrefix
        payload["middle_name"] = contact.middleName
        payload["previous_family_name"] = contact.previousFamilyName
        payload["name_suffix"] = contact.nameSuffix
        payload["email_addresses"] = stringLabeledValues(contact.emailAddresses)
        payload["phone_numbers"] = phonePayloads(contact.phoneNumbers)
        payload["postal_addresses"] = postalPayloads(contact.postalAddresses)
        payload["url_addresses"] = stringLabeledValues(contact.urlAddresses)
        payload["birthday"] = dateComponentsPayload(contact.birthday)
        payload["dates"] = datedPayloads(contact.dates)
        payload["social_profiles"] = socialPayloads(contact.socialProfiles)
        payload["instant_message_addresses"] = instantMessagePayloads(contact.instantMessageAddresses)
        payload["contact_relations"] = relationPayloads(contact.contactRelations)
    }
    return payload
}

func matches(_ contact: CNContact, query: String) -> Bool {
    if query.isEmpty {
        return true
    }
    let haystack = [
        displayName(contact),
        contact.givenName,
        contact.familyName,
        contact.nickname,
        contact.organizationName,
        contact.departmentName,
        contact.jobTitle,
    ].joined(separator: " ").lowercased()
    return haystack.contains(query)
}

let input = FileHandle.standardInput.readDataToEndOfFile()
guard
    let object = try? JSONSerialization.jsonObject(with: input, options: []),
    let request = object as? [String: Any]
else {
    emit([
        "schema_version": 1,
        "status": "error",
        "source": "contacts",
        "warnings": [warning("invalid_request", "Expected JSON request.")],
    ])
}

let command = stringValue(request, "command")

if command == "contacts" {
    let store = ensureAccess()!
    let query = stringValue(request, "query").lowercased()
    let limit = max(1, min(intValue(request, "limit", 20), 10000))
    let maxContacts = max(1, min(intValue(request, "max_contacts", 10000), 10000))
    let fetch = CNContactFetchRequest(keysToFetch: baseKeys)
    fetch.sortOrder = .userDefault
    fetch.unifyResults = true

    var scanned = 0
    var scanTruncated = false
    var results: [[String: Any]] = []
    do {
        try store.enumerateContacts(with: fetch) { contact, stop in
            if scanned >= maxContacts {
                scanTruncated = true
                stop.pointee = true
                return
            }
            scanned += 1
            if !matches(contact, query: query) {
                return
            }
            results.append(contactPayload(contact, includeDetails: false))
            if results.count >= limit {
                stop.pointee = true
            }
        }
    } catch {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "contacts": [],
            "warnings": [warning("contacts_fetch_failed", "Contacts could not be fetched safely.")],
        ])
    }

    var warnings: [[String: String]] = []
    if scanTruncated {
        warnings.append(warning("scan_truncated", "Contacts scan stopped at the scan limit."))
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
        "contacts": results,
        "scanned": scanned,
        "warnings": warnings,
    ])
}

if command == "contact_by_id" {
    let store = ensureAccess()!
    let contactId = stringValue(request, "contact_id")
    if contactId.isEmpty {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "contacts",
            "contact": NSNull(),
            "warnings": [warning("invalid_contact_id", "Expected Contacts identifier.")],
        ])
    }
    do {
        let contact = try store.unifiedContact(withIdentifier: contactId, keysToFetch: baseKeys)
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "contact": contactPayload(contact, includeDetails: true),
            "warnings": [],
        ])
    } catch {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "contacts",
            "contact": NSNull(),
            "warnings": [],
        ])
    }
}

emit([
    "schema_version": 1,
    "status": "error",
    "source": "contacts",
    "warnings": [warning("unknown_command", "Unsupported Contacts helper command.")],
])
