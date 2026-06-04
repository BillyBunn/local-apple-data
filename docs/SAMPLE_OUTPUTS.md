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

## Notes Plan

```json
{
  "status": "ok",
  "source": "notes",
  "mode": "plan",
  "mutation_applied": false,
  "apply_available": true,
  "preview": {
    "operation": "create",
    "target": {
      "account": "default",
      "folder": "default"
    },
    "proposed": {
      "kind": "note",
      "format": "plaintext",
      "title": "Synthetic planned note",
      "body_chars": 20,
      "body_preview_text": "Synthetic note body.",
      "body_preview_chars": 20,
      "body_preview_truncated": false
    },
    "idempotency_key": "notes-plan:v1:<hash>",
    "approval": {
      "required_for_apply": true,
      "apply_tool_available": true,
      "approval_fingerprint": "<hash>",
      "approval_token_format": "notes-apply:v1:<approval_fingerprint>"
    }
  },
  "warnings": []
}
```

## Notes Apply

```json
{
  "status": "ok",
  "source": "notes",
  "mode": "apply",
  "mutation_applied": true,
  "idempotency_key": "notes-plan:v1:<hash>",
  "approval": {
    "approval_fingerprint": "<hash>",
    "approval_token_verified": true
  },
  "read_back": {
    "handle": "<opaque notes:note:v2 handle>",
    "title": "Synthetic planned note",
    "content_chars": 42,
    "truncated": false
  },
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
  "tool_count": 43,
  "mail_content_status": "ok",
  "mail_plan_status": "ok",
  "mail_plan_mutation_applied": false,
  "mail_plan_apply_available": true,
  "mail_apply_status": "ok",
  "mail_apply_mutation_applied": true,
  "notes_content_status": "ok",
  "notes_plan_status": "ok",
  "notes_plan_mutation_applied": false,
  "notes_plan_apply_available": true,
  "notes_apply_status": "ok",
  "notes_apply_mutation_applied": true,
  "icloud_drive_content_status": "ok",
  "icloud_plan_status": "ok",
  "icloud_plan_mutation_applied": false,
  "icloud_plan_apply_available": true,
  "icloud_apply_status": "ok",
  "icloud_apply_mutation_applied": true,
  "calendar_detail_status": "ok",
  "calendar_plan_status": "ok",
  "calendar_plan_mutation_applied": false,
  "calendar_plan_apply_available": true,
  "calendar_apply_status": "ok",
  "calendar_apply_mutation_applied": true,
  "contacts_detail_status": "ok",
  "contacts_plan_status": "ok",
  "contacts_plan_mutation_applied": false,
  "contacts_plan_apply_available": true,
  "contacts_apply_status": "ok",
  "contacts_apply_mutation_applied": true,
  "photos_detail_status": "ok",
  "photos_export_status": "ok",
  "photos_plan_status": "ok",
  "photos_plan_mutation_applied": false,
  "photos_plan_apply_available": true,
  "photos_apply_status": "ok",
  "photos_apply_mutation_applied": true,
  "messages_transcript_status": "ok",
  "voice_memos_transcript_status": "ok",
  "voice_memos_export_status": "ok",
  "hide_my_email_detail_status": "ok",
  "reminders_content_status": "ok",
  "reminders_plan_status": "ok",
  "reminders_plan_mutation_applied": false,
  "reminders_plan_apply_available": true,
  "reminders_apply_status": "ok",
  "reminders_apply_mutation_applied": true
}
```

## Contacts Plan

```json
{
  "status": "ok",
  "source": "contacts",
  "mode": "plan",
  "mutation_applied": false,
  "apply_available": true,
  "preview": {
    "operation": "create",
    "target": {
      "container": "default_contacts_container"
    },
    "proposed": {
      "contact_type": "person",
      "given_name": "Synthetic",
      "family_name": "Created",
      "organization_name": "Example Org",
      "email_count": 1,
      "phone_count": 1,
      "url_count": 1,
      "note_status": "blocked",
      "image_data": "blocked"
    },
    "idempotency_key": "contacts-plan:v1:<hash>",
    "approval": {
      "required_for_apply": true,
      "apply_tool_available": true,
      "approval_fingerprint": "<hash>",
      "approval_token_format": "contacts-apply:v1:<approval_fingerprint>"
    }
  },
  "warnings": []
}
```

## Contacts Apply

```json
{
  "status": "ok",
  "source": "contacts",
  "mode": "apply",
  "operation": "create",
  "mutation_applied": true,
  "apply_available": true,
  "idempotency_key": "contacts-plan:v1:<hash>",
  "approval": {
    "approval_fingerprint": "<hash>",
    "approval_token_verified": true
  },
  "read_back": {
    "handle": "<opaque contacts:contact:v1 handle>",
    "display_name": "Synthetic Created",
    "contact_type": "person",
    "given_name": "Synthetic",
    "family_name": "Created",
    "email_count": 1,
    "phone_count": 1,
    "note_status": "requires_entitlement"
  },
  "warnings": []
}
```

## Calendar Plan

```json
{
  "status": "ok",
  "source": "calendar",
  "mode": "plan",
  "mutation_applied": false,
  "apply_available": true,
  "preview": {
    "operation": "create",
    "target": {
      "calendar_title": "Synthetic Calendar"
    },
    "proposed": {
      "title": "Synthetic planned event",
      "start_date": "2026-06-04T19:00:00Z",
      "end_date": "2026-06-04T20:00:00Z",
      "all_day": false,
      "location_present": true,
      "notes_present": true,
      "attendees_count": 0
    },
    "idempotency_key": "calendar-plan:v1:<hash>",
    "approval": {
      "required_for_apply": true,
      "apply_tool_available": true,
      "approval_fingerprint": "<hash>",
      "approval_token_format": "calendar-apply:v1:<approval_fingerprint>"
    }
  },
  "warnings": []
}
```

## Calendar Apply

```json
{
  "status": "ok",
  "source": "calendar",
  "mode": "apply",
  "operation": "create",
  "mutation_applied": true,
  "apply_available": true,
  "idempotency_key": "calendar-plan:v1:<hash>",
  "approval": {
    "approval_fingerprint": "<hash>",
    "approval_token_verified": true
  },
  "read_back": {
    "handle": "<opaque calendar:event:v1 handle>",
    "title": "Synthetic planned event",
    "calendar_title": "Synthetic Calendar",
    "start_date": "2026-06-04T19:00:00Z",
    "end_date": "2026-06-04T20:00:00Z",
    "all_day": false
  },
  "warnings": []
}
```

## iCloud Drive Plan

```json
{
  "status": "ok",
  "source": "icloud_drive",
  "mode": "plan",
  "mutation_applied": false,
  "apply_available": true,
  "preview": {
    "operation": "create_text",
    "target": {
      "parent_handle": "<opaque icloud:file:v1 folder handle>",
      "filename": "synthetic-note.md"
    },
    "proposed": {
      "kind": "file",
      "content_type": "text",
      "content_chars": 27,
      "extension": ".md"
    },
    "idempotency_key": "icloud-drive-plan:v1:<hash>",
    "approval": {
      "required_for_apply": true,
      "apply_tool_available": true,
      "approval_fingerprint": "<hash>",
      "approval_token_format": "icloud-drive-apply:v1:<approval_fingerprint>"
    }
  },
  "warnings": []
}
```

## iCloud Drive Apply

```json
{
  "status": "ok",
  "source": "icloud_drive",
  "mode": "apply",
  "operation": "create_text",
  "mutation_applied": true,
  "apply_available": true,
  "idempotency_key": "icloud-drive-plan:v1:<hash>",
  "approval": {
    "approval_fingerprint": "<hash>",
    "approval_token_verified": true
  },
  "read_back": {
    "handle": "<opaque icloud:file:v1 handle>",
    "name": "synthetic-note.md",
    "kind": "file",
    "content_chars": 27,
    "content_sha256": "<sha256>"
  },
  "warnings": []
}
```

## Reminders Plan

```json
{
  "status": "ok",
  "source": "reminders",
  "mode": "plan",
  "mutation_applied": false,
  "apply_available": true,
  "preview": {
    "operation": "create",
    "target": {
      "list_name": "Synthetic List"
    },
    "proposed": {
      "title": "Synthetic planned reminder",
      "due_date": "2026-06-04",
      "notes_present": false
    },
    "idempotency_key": "reminders-plan:v1:<hash>",
    "approval": {
      "required_for_apply": true,
      "apply_tool_available": true,
      "approval_fingerprint": "<hash>",
      "approval_token_format": "reminders-apply:v1:<approval_fingerprint>"
    }
  },
  "warnings": []
}
```

## Reminders Apply

```json
{
  "status": "ok",
  "source": "reminders",
  "mode": "apply",
  "operation": "complete",
  "mutation_applied": true,
  "apply_available": true,
  "idempotency_key": "reminders-plan:v1:<hash>",
  "approval": {
    "approval_fingerprint": "<hash>",
    "approval_token_verified": true
  },
  "read_back": {
    "handle": "<opaque reminders:reminder:eventkit:v1 handle>",
    "title": "Synthetic planned reminder",
    "list_name": "Synthetic List",
    "due_date": "2026-06-04",
    "completed": true,
    "notes_present": false
  },
  "warnings": []
}
```
