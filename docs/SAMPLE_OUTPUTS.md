# Sample Outputs

These examples are synthetic. They are shape examples only and must not be replaced with live personal content in public docs.

## Health

```json
{
  "schema_version": 1,
  "status": "ok",
  "privacy": {
    "content_inspected": false,
    "raw_rows_inspected": false,
    "credentials_inspected": false,
    "output_tier": "health"
  },
  "warnings": [],
  "surfaces": {
    "mail": {"status": "ok", "content_status_supported": true},
    "messages": {"status": "ok"},
    "hide_my_email": {"status": "ok", "authoritative_inventory": false},
    "voice_memos": {"status": "ok"},
    "notes": {"status": "ok", "automation_check": "on_exact_content_call"},
    "calendar": {"status": "checked_on_tool_call", "permission_check": "non_prompting_eventkit", "prompts": false},
    "reminders": {"status": "ok", "eventkit_check": "on_tool_call"},
    "contacts": {"status": "checked_on_tool_call", "permission_check": "non_prompting_contacts_framework", "prompts": false},
    "photos": {"status": "checked_on_tool_call", "permission_check": "non_prompting_photokit", "prompts": false},
    "icloud_drive": {"status": "ok", "schema_check": "not_applicable"}
  },
  "schema_checks": {
    "mail": {"status": "ok", "warnings": []},
    "messages": {"status": "ok", "warnings": []},
    "voice_memos": {"status": "ok", "warnings": []},
    "notes": {"status": "ok", "warnings": []},
    "reminders": {"status": "ok", "warnings": []}
  },
  "access_requirements": [
    {"surface": "calendar", "check_mode": "non_prompting_eventkit", "prompts": false},
    {"surface": "contacts", "check_mode": "non_prompting_contacts_framework", "prompts": false},
    {"surface": "photos", "check_mode": "non_prompting_photokit", "prompts": false}
  ]
}
```

## Mail Search

```json
{
  "status": "ok",
  "query": "review packet",
  "results": [
    {
      "handle": "<opaque mail:message:v2 handle>",
      "subject": "Review packet",
      "date_received": "2026-06-04T09:30:00Z",
      "mailbox": "Inbox",
      "content_status": "available"
    }
  ],
  "warnings": []
}
```

## Notes Content

```json
{
  "status": "ok",
  "handle": "<opaque notes:note:v2 handle>",
  "content": "Synthetic note body text.",
  "content_chars": 25,
  "truncated": false,
  "warnings": []
}
```

## Hide My Email Search

```json
{
  "status": "ok",
  "authoritative_inventory": false,
  "results": [
    {
      "handle": "<opaque hide_my_email:alias:v1 handle>",
      "masked_alias": "ab***@privaterelay.appleid.com",
      "domain": "privaterelay.appleid.com",
      "inference_kind": "private_relay",
      "confidence": "high",
      "message_count": 3,
      "provenance": "local_mail_address_metadata"
    }
  ],
  "warnings": []
}
```

Exact Hide My Email detail returns the selected full alias only after the matching opaque handle is supplied. Public examples should keep that value as a placeholder.

## Runtime Verifier

```json
{
  "status": "ok",
  "tool_count": 29,
  "mail_content_status": "ok",
  "notes_content_status": "ok",
  "icloud_drive_content_status": "ok",
  "calendar_detail_status": "ok",
  "contacts_detail_status": "ok",
  "photos_detail_status": "ok",
  "photos_export_status": "ok",
  "messages_transcript_status": "ok",
  "voice_memos_transcript_status": "ok",
  "voice_memos_export_status": "ok",
  "hide_my_email_detail_status": "ok",
  "reminders_content_status": "ok"
}
```
