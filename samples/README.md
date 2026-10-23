# Samples

* `sample_captures.json`: a sync batch you can POST to a running server to populate the Inbox without a phone:

```
curl -X POST http://127.0.0.1:8765/api/sync/captures -H "Content-Type: application/json" -H "X-ReelVault-Token: <token from Settings>" --data @samples/sample_captures.json
```

* `sample_config.json`: shape of the optional `%LOCALAPPDATA%\ReelVault\Data\config.json` (copy, fill in, never commit).
* `sample_brief.json`: an example of the validated creative-brief schema the AI analysis produces.
