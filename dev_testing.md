## 1. Prepare the Environment

blah ...

### 1.1. Looking at the logs

For the supprting services, assuming these were installed as per the installation, one can use *journalctl*, like:
- `journalctl -ef -uollama`
- `journalctl -ef -uweaviate`
- `journalctl -ef -uphoenix` - though this is likely not that important

This instructs *journalctl* to:
- `-e` - jump to the end of the logs
- `-f` - follow the logs, like *tail*
- `-u` - filter for the service unit's logs

## 2. Launch the Backend

`make run-be`

## 3. Initialize the Environment

`./dist/ragadmin --config ~/.config/ragcli/config.yaml --socket /tmp/ragcli/backend.sock init` or simply `RA init` assuming the aliases were created.

## 4. Verify Dependencies and Storage

`./dist/ragadmin --config ~/.config/ragcli/config.yaml --socket /tmp/ragcli/backend.sock health` or simply `RA health`

## 5. Reindex the Knowledge Base

`./dist/ragadmin --config ~/.config/ragcli/config.yaml --socket /tmp/ragcli/backend.sock reindex` or simply `RA reindex`

## Notes

simple aliases to help dev testing: 

`alias RA="./dist/ragadmin --config ~/.config/ragcli/config.yaml --socket /tmp/ragcli/backend.sock"`
`alias RM="./dist/ragman --socket /tmp/ragcli/backend.sock"`