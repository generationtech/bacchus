# BACCHUS

Creates multi-volume backups, first compressing and then encrypting.
Allows for creating smaller backups with privacy while allowing
for partial recovery should any individual incremental archive
file be damaged.

Other similar solutions using encryption result in total data
loss past failed incremental archive file.

## Help

Access program command line options with

    bacchus --help

## Building

argbash located outside of repo dir was used for building the command line argument parsing

script built with

    ../argbash/bin/argbash source/bacchus.m4 -o bacchus.sh

then parser script built with

    ../argbash/bin/argbash --strip user-content "source/bacchus-parsing.m4" -o "scripts/bacchus-parsing.sh"
