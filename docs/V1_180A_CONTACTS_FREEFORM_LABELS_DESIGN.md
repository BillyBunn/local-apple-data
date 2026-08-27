# v1.180A Contacts Free-Form Custom Labels

Status: Apply-capable implementation (policy change to an existing gate).

Approved write tools: `local-apple-data contacts apply` and `contacts_apply_change`
(unchanged). This document does not introduce any new tool.

This is an operator-authorized lift of the Contacts custom-label normalization cap. It
reverses the "custom labels beyond bounded local labels" restriction for the label
string itself while keeping every other part of the Contacts create/update gate
unchanged.

## Prior behavior

Custom labels on emails, phones, URLs, postal addresses, dates, social profiles,
instant-message addresses, and contact relations were normalized to a 64-character,
lowercased, `space -> underscore` form (`_normalize_label` /
`_normalize_labeled_values`, `MAX_LABEL_CHARS = 64`). A label like `My Custom Label`
was silently rewritten to `my_custom_label`.

## New behavior

Contacts.framework `CNLabeledValue` accepts arbitrary label strings, and the Swift
helper already passes non-standard labels through verbatim (`contactsLabel` returns
the input for any non-canonical label). The Python layer now preserves the caller's
exact label string:

- No lowercasing and no `space -> underscore` normalization. A label round-trips
  verbatim (exact case, spaces, and punctuation).
- Bounded to a finite `MAX_LABEL_CHARS = 255`. A label longer than 255 characters
  (after trimming surrounding whitespace) is refused at plan time with
  `label_too_large`, not silently truncated.
- Control characters (any code point below `0x20` plus `0x7F`, which includes
  newlines and tabs) and NUL are refused at plan time with `invalid_label`, not
  silently stripped.
- An empty or whitespace-only label still defaults to `other`.

The single helper `_normalize_freeform_label(value, field=...)` implements this and is
used by every labeled-field normalizer, so the behavior is uniform across scalar,
method, and rich fields. The check order rejects control characters before the length
check so a control-only oversize string is reported as invalid.

## What is unchanged

Everything else about the create/update gate is byte-for-byte unchanged: the
expected-state binding (`update_safe_sha256`), the per-field count caps
(`MAX_CONTACT_METHODS`, `MAX_CONTACT_RICH_VALUES`), the per-value length cap
(`MAX_PREVIEW_FIELD_CHARS`), the approval token, explicit confirmation, and the
detail read-back. The known standard labels (`home`, `work`, `mobile`, `iphone`,
`main`, `home_fax`, `work_fax`, `other`) still map to their `CNLabel*` constants in
the Swift helper.

## Synthetic Tests Required

- A label with spaces, mixed case, and punctuation round-trips verbatim through
  create and rich-field update plans.
- A label of exactly 255 characters is allowed and preserved verbatim.
- A label of 256 characters is refused with `label_too_large`.
- A label containing a newline, tab, or NUL is refused with `invalid_label`.
- An empty/whitespace label defaults to `other`.
- Runtime verifier coverage for the round-trip, the 255-char boundary, and the
  oversize/control-char refusals.

The current release allows Contacts free-form custom labels preserved verbatim up to 255 characters, rejecting only control characters and oversize labels, through the existing exact scalar/method/rich-field update and create gates only.
