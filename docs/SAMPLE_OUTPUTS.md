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
    "safari": {"status": "ok", "schema_check": "not_applicable"},
    "shortcuts": {"status": "available", "schema_check": "not_applicable"},
    "books": {"status": "ok", "schema_check": "ok"},
    "podcasts": {"status": "ok", "schema_check": "ok"},
    "music": {"status": "available", "schema_check": "not_applicable", "automation_check": "on_exact_tool_call"},
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
    "books": {"status": "ok", "warnings": []},
    "podcasts": {"status": "ok", "warnings": []},
    "notes": {"status": "ok", "warnings": []},
    "reminders": {"status": "ok", "warnings": []}
  },
  "access_requirements": [
    {"surface": "books", "check_mode": "schema_only", "prompts": false},
    {"surface": "podcasts", "check_mode": "schema_only", "prompts": false},
    {"surface": "music", "check_mode": "app_and_osascript_availability_without_automation_probe", "prompts": false},
    {"surface": "calendar", "check_mode": "non_prompting_eventkit", "prompts": false},
    {"surface": "contacts", "check_mode": "non_prompting_contacts_framework", "prompts": false},
    {"surface": "photos", "check_mode": "non_prompting_photokit", "prompts": false}
  ]
}
```

## Podcasts Search

```json
{
  "status": "ok",
  "source": "podcasts",
  "results": [
    {
      "handle": "<opaque podcasts:show:v1 handle>",
      "title": "Synthetic Show",
      "author": "Synthetic Host",
      "category": "Technology",
      "episode_count": 12,
      "feed_url_returned": false,
      "webpage_url_returned": false,
      "raw_identifier_returned": false
    }
  ],
  "warnings": []
}
```

## Podcasts Episodes

```json
{
  "status": "ok",
  "source": "podcasts",
  "result": {
    "handle": "<opaque podcasts:show:v1 handle>",
    "title": "Synthetic Show",
    "episodes": [
      {
        "handle": "<opaque podcasts:episode:v1 handle>",
        "title": "Synthetic Episode",
        "duration_seconds": 1800.0,
        "transcript_status": "available",
        "description_returned": false,
        "transcript_text_returned": false,
        "audio_content_returned": false,
        "raw_identifier_returned": false
      }
    ],
    "episodes_returned": 1
  },
  "warnings": []
}
```

## Podcasts Episode Detail

```json
{
  "status": "ok",
  "source": "podcasts",
  "result": {
    "handle": "<opaque podcasts:episode:v1 handle>",
    "title": "Synthetic Episode",
    "description": "Synthetic bounded episode description.",
    "description_chars": 38,
    "description_truncated": false,
    "transcript_text_returned": false,
    "audio_content_returned": false,
    "raw_identifier_returned": false
  },
  "warnings": []
}
```

## Music Search

```json
{
  "status": "ok",
  "source": "music",
  "results": [
    {
      "handle": "<opaque music:track:v1 handle>",
      "title": "Synthetic Track",
      "artist": "Synthetic Artist",
      "album": "Synthetic Album",
      "genre": "Reference",
      "duration_seconds": 180.0,
      "audio_content_returned": false,
      "lyrics_returned": false,
      "file_path_returned": false,
      "raw_identifier_returned": false,
      "play_history_returned": false,
      "rating_returned": false
    }
  ],
  "warnings": []
}
```

## Music Playlists

```json
{
  "status": "ok",
  "source": "music",
  "results": [
    {
      "handle": "<opaque music:playlist:v1 handle>",
      "title": "Synthetic Playlist",
      "kind": "user",
      "track_count": 12,
      "duration_seconds": 2160.0,
      "playlist_tracks_returned": false,
      "raw_identifier_returned": false
    }
  ],
  "warnings": []
}
```

## TV Search

```json
{
  "status": "ok",
  "source": "tv",
  "results": [
    {
      "handle": "<opaque tv:item:v1 handle>",
      "title": "Synthetic Episode",
      "show": "Synthetic Show",
      "artist": "Synthetic Studio",
      "genre": "Reference",
      "video_kind": "TV show",
      "duration_seconds": 1800.0,
      "season_number": 1,
      "episode_number": 2,
      "video_content_returned": false,
      "file_path_returned": false,
      "artwork_returned": false,
      "description_returned": false,
      "playback_state_returned": false,
      "watched_state_returned": false,
      "raw_identifier_returned": false
    }
  ],
  "warnings": []
}
```

## TV Playlists

```json
{
  "status": "ok",
  "source": "tv_playlists",
  "results": [
    {
      "handle": "<opaque tv:playlist:v1 handle>",
      "title": "Synthetic TV Playlist",
      "kind": "user",
      "item_count": 4,
      "duration_seconds": 7200.0,
      "playlist_items_returned": false,
      "raw_identifier_returned": false
    }
  ],
  "warnings": []
}
```

## Freeform Boards

```json
{
  "status": "ok",
  "source": "freeform",
  "results": [
    {
      "handle": "<opaque freeform:board:v1 handle>",
      "title_status": "unavailable_without_blob_decode",
      "board_title_returned": false,
      "last_activity_at": "2026-06-04T12:00:00+00:00",
      "is_favorite": true,
      "item_count": 12,
      "asset_reference_count": 3,
      "board_items_returned": false,
      "board_content_returned": false,
      "asset_content_returned": false,
      "raw_identifier_returned": false
    }
  ],
  "warnings": []
}
```

## Freeform Folders

```json
{
  "status": "ok",
  "source": "freeform",
  "results": [
    {
      "handle": "<opaque freeform:folder:v1 handle>",
      "title": "Synthetic Folder",
      "board_count": 4,
      "folder_blob_returned": false,
      "raw_identifier_returned": false
    }
  ],
  "warnings": []
}
```

## Books Search

```json
{
  "status": "ok",
  "source": "books",
  "results": [
    {
      "handle": "<opaque books:book:v1 handle>",
      "title": "Synthetic Book",
      "author": "Synthetic Author",
      "genre": "Reference",
      "kind": "epub",
      "reading_progress": 0.42,
      "annotation_count": 2,
      "book_text_returned": false,
      "raw_identifier_returned": false
    }
  ],
  "warnings": []
}
```

## Books Exact Item

```json
{
  "status": "ok",
  "source": "books",
  "result": {
    "handle": "<opaque books:book:v1 handle>",
    "title": "Synthetic Book",
    "author": "Synthetic Author",
    "genre": "Reference",
    "annotation_count": 2,
    "book_text_returned": false,
    "raw_identifier_returned": false
  },
  "warnings": []
}
```

## Books Annotations

```json
{
  "status": "ok",
  "source": "books",
  "book_handle": "<opaque books:book:v1 handle>",
  "results": [
    {
      "handle": "<opaque books:annotation:v1 handle>",
      "selected_text": "Synthetic highlighted text.",
      "note_text": "Synthetic reader note.",
      "annotation_text_returned": true,
      "raw_identifier_returned": false
    }
  ],
  "warnings": []
}
```

## Safari Search

```json
{
  "status": "ok",
  "source": "safari",
  "results": [
    {
      "handle": "<opaque safari:item:v1 handle>",
      "title": "Synthetic Bookmark",
      "kind": "bookmark",
      "url_domain": "example.com",
      "url_scheme": "https",
      "url_has_query": true,
      "url_path_depth": 2
    }
  ],
  "warnings": []
}
```

## Safari Exact Item

```json
{
  "status": "ok",
  "source": "safari",
  "result": {
    "handle": "<opaque safari:item:v1 handle>",
    "title": "Synthetic Bookmark",
    "kind": "bookmark",
    "url_domain": "example.com",
    "url": "https://example.com/private/path?example=1"
  },
  "warnings": []
}
```

## Shortcuts Search

```json
{
  "status": "ok",
  "source": "shortcuts",
  "results": [
    {
      "handle": "<opaque shortcuts:item:v1 handle>",
      "title": "Synthetic Shortcut",
      "kind": "shortcut",
      "identifier_present": true,
      "shortcut_body_returned": false
    }
  ],
  "warnings": []
}
```

## Shortcuts Exact Item

```json
{
  "status": "ok",
  "source": "shortcuts",
  "result": {
    "handle": "<opaque shortcuts:item:v1 handle>",
    "title": "Synthetic Shortcut",
    "kind": "shortcut",
    "identifier_present": true,
    "shortcut_body_returned": false
  },
  "warnings": []
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

## Mail Attachments

```json
{
  "status": "ok",
  "source": "mail",
  "results": [
    {
      "handle": "<opaque mail:attachment:v1 handle>",
      "message_handle": "<opaque mail:message:v2 handle>",
      "filename": "review-packet.pdf",
      "content_type": "application/pdf",
      "file_size": 123456,
      "attachment_type": "document",
      "media_status": "available",
      "attachment_content_returned": false,
      "attachment_content_exported": false
    }
  ],
  "warnings": []
}
```

## Mail Attachment Export

```json
{
  "status": "ok",
  "source": "mail",
  "result": {
    "handle": "<opaque mail:attachment:v1 handle>",
    "message_handle": "<opaque mail:message:v2 handle>",
    "filename": "review-packet.pdf",
    "attachment_content_returned": false,
    "attachment_content_exported": true,
    "exported_filename": "review-packet.pdf",
    "exported_bytes": 123456
  },
  "warnings": []
}
```

## Messages Transcript

```json
{
  "status": "ok",
  "source": "messages",
  "result": {
    "handle": "<opaque messages:chat:v1 handle>",
    "messages_returned": 2,
    "transcript_chars": 49,
    "transcript_truncated": false,
    "messages": [
      {
        "date": "2026-06-04T09:30:00Z",
        "direction": "received",
        "service": "iMessage",
        "text": "Synthetic text-column message.",
        "text_source": "text",
        "text_chars": 30,
        "text_truncated": false
      },
      {
        "date": "2026-06-04T09:31:00Z",
        "direction": "sent",
        "service": "iMessage",
        "text": "Synthetic fallback.",
        "text_source": "attributed_body",
        "text_chars": 19,
        "text_truncated": false
      }
    ]
  },
  "warnings": []
}
```

## Messages Attachments

```json
{
  "status": "ok",
  "source": "messages",
  "results": [
    {
      "handle": "<opaque messages:attachment:v1 handle>",
      "chat_handle": "<opaque messages:chat:v1 handle>",
      "filename": "image.jpeg",
      "mime_type": "image/jpeg",
      "uti": "public.jpeg",
      "file_size": 123456,
      "attachment_type": "image",
      "media_status": "available",
      "attachment_content_returned": false,
      "attachment_content_exported": false
    }
  ],
  "warnings": []
}
```

## Messages Attachment Export

```json
{
  "status": "ok",
  "source": "messages",
  "result": {
    "handle": "<opaque messages:attachment:v1 handle>",
    "chat_handle": "<opaque messages:chat:v1 handle>",
    "filename": "image.jpeg",
    "attachment_content_returned": false,
    "attachment_content_exported": true,
    "exported_filename": "image.jpeg",
    "exported_bytes": 123456
  },
  "warnings": []
}
```

## Messages Send-Text Plan

```json
{
  "status": "ok",
  "source": "messages",
  "mode": "plan",
  "mutation_applied": false,
  "apply_available": true,
  "preview": {
    "operation": "send_text",
    "target": {
      "handle": "<opaque messages:chat:v1 handle>",
      "display_name": "Synthetic Chat",
      "service_name": "iMessage",
      "participants_count": 1,
      "message_count": 12,
      "last_message_date": "2026-06-04T09:31:00+00:00",
      "last_message_rowid": 1200
    },
    "proposed": {
      "kind": "messages_send_text",
      "format": "plaintext",
      "body_chars": 29,
      "body_preview_text": "Synthetic outgoing message.",
      "body_preview_chars": 29,
      "body_preview_truncated": false,
      "attachments_permitted": false,
      "direct_recipient_send_permitted": false
    },
    "idempotency_key": "messages-plan:v1:<hash>",
    "approval": {
      "required_for_apply": true,
      "apply_tool_available": true,
      "approval_fingerprint": "<hash>",
      "approval_token_format": "messages-apply:v1:<approval_fingerprint>"
    },
    "read_back_required_after_apply": true
  },
  "warnings": []
}
```

## Messages Send-Text Apply

```json
{
  "status": "ok",
  "source": "messages",
  "mode": "apply",
  "mutation_applied": true,
  "idempotency_key": "messages-plan:v1:<hash>",
  "approval": {
    "approval_fingerprint": "<hash>",
    "approval_token_verified": true
  },
  "read_back": {
    "chat_handle_confirmed": true,
    "message_date": "2026-06-04T09:32:00+00:00",
    "direction": "sent",
    "service": "iMessage",
    "text_source": "text",
    "body_chars": 29,
    "body_sha256": "<sha256>"
  },
  "warnings": []
}
```

## Notes Content

```json
{
  "status": "ok",
  "source": "notes",
  "result": {
    "handle": "<opaque notes:note:v2 handle>",
    "content_text": "Synthetic note body text.",
    "content_chars": 25,
    "content_sha256": "<sha256>",
    "truncated": false
  },
  "warnings": []
}
```

## Notes Attachments

```json
{
  "status": "ok",
  "source": "notes",
  "results": [
    {
      "handle": "<opaque notes:attachment:v1 handle>",
      "note_handle": "<opaque notes:note:v2 handle>",
      "filename": "scan-packet.pdf",
      "file_size": 123456,
      "type_uti": "com.adobe.pdf",
      "attachment_type": "document",
      "media_status": "available",
      "blob_status": "unavailable",
      "attachment_content_returned": false,
      "attachment_content_exported": false
    }
  ],
  "warnings": []
}
```

## Notes Attachment Export

```json
{
  "status": "ok",
  "source": "notes",
  "result": {
    "handle": "<opaque notes:attachment:v1 handle>",
    "filename": "scan-packet.pdf",
    "attachment_content_returned": false,
    "attachment_content_exported": true,
    "exported_filename": "scan-packet.pdf",
    "exported_bytes": 123456
  },
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

## Notes Append Plan

```json
{
  "status": "ok",
  "source": "notes",
  "mode": "plan",
  "mutation_applied": false,
  "apply_available": true,
  "preview": {
    "operation": "append_text",
    "target": {
      "handle": "<opaque notes:note:v2 handle>",
      "expected_current_sha256": "<sha256>"
    },
    "proposed": {
      "kind": "note",
      "format": "plaintext_append",
      "append_chars": 20,
      "append_preview_text": "Synthetic append body.",
      "overwrite": "blocked",
      "delete": "blocked"
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

## Notes Append Apply

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
    "content_chars": 62,
    "content_sha256": "<sha256>",
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
  "tool_count": 74,
  "mail_content_status": "ok",
  "mail_plan_status": "ok",
  "mail_plan_mutation_applied": false,
  "mail_plan_apply_available": true,
  "mail_apply_status": "ok",
  "mail_apply_mutation_applied": true,
  "mail_attachment_list_status": "ok",
  "mail_attachment_export_status": "ok",
  "mail_attachment_content_exported": true,
  "notes_content_status": "ok",
  "notes_content_sha256_present": true,
  "notes_plan_status": "ok",
  "notes_plan_mutation_applied": false,
  "notes_plan_apply_available": true,
  "notes_apply_status": "ok",
  "notes_apply_mutation_applied": true,
  "notes_append_plan_status": "ok",
  "notes_append_apply_status": "ok",
  "notes_append_apply_mutation_applied": true,
  "notes_append_stale_warning": "current_content_changed",
  "notes_attachment_list_status": "ok",
  "notes_attachment_export_status": "ok",
  "notes_attachment_content_exported": true,
  "icloud_drive_content_status": "ok",
  "icloud_content_sha256_present": true,
  "icloud_plan_status": "ok",
  "icloud_plan_mutation_applied": false,
  "icloud_plan_apply_available": true,
  "icloud_apply_status": "ok",
  "icloud_apply_mutation_applied": true,
  "icloud_append_plan_status": "ok",
  "icloud_append_apply_status": "ok",
  "icloud_append_apply_mutation_applied": true,
  "icloud_append_stale_warning": "current_content_changed",
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
  "messages_attachment_list_status": "ok",
  "messages_attachment_export_status": "ok",
  "messages_attachment_content_exported": true,
  "messages_plan_status": "ok",
  "messages_plan_mutation_applied": false,
  "messages_plan_apply_available": true,
  "messages_apply_status": "ok",
  "messages_apply_mutation_applied": true,
  "messages_apply_body_not_returned": true,
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
