# AER Runtime Resume Summary Contract v1

## Contract

Resume Summary v1 is the public contract returned by `runtime_resume_marker_to_summary(...)`.

The fixed payload is:

- `contract`: `aer.runtime.resume_marker.summary.v1`
- `valid`: summary structural validity as a boolean
- `outcome`: the Resume Marker's own runtime-visible result
- `status`: summary structural validity as vocabulary
- `reason`: generic summary reason

## Valid Summary

Valid Resume Summary v1 payloads use:

- `valid`: `True`
- `status`: `valid`
- `reason`: `None`

`outcome` is the Resume Marker's own runtime-visible result.

## Invalid Summary

Invalid Resume Summary v1 payloads use:

- `valid`: `False`
- `outcome`: the Resume Marker outcome when it can be read from the marker; otherwise `continue`
- `status`: `invalid`
- `reason`: `invalid resume marker contract`

Invalid summaries must not copy internal or upstream error text.

## Leak Seal

Resume Summary v1 must not:

- expose `runtime_resume_marker`
- pass through the marker object
- leak wrapper fields recursively
- copy internal or upstream error text
- expose wrapper, view, or object surfaces
- add Snapshot, persistence, replay, journal, or audit behavior
