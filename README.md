# BACCHUS

Creates multi-volume backups, first compressing and then encrypting.
Allows for creating smaller backups with privacy while allowing
for partial recovery should any individual incremental archive
file be damaged.

Other similar solutions using encryption result in total data
loss past failed incremental archive file.

## Building

argbash located outside of repo dir was used for building the command line argument parsing

script built with

../argbash/bin/argbash source/bacchus.m4 -o bacchus.sh

then parser script built with

../argbash/bin/argbash --strip user-content "source/bacchus-parsing.m4" -o "scripts/bacchus-parsing.sh"

## Notes

1) Due to the way gpg now handles passwords on command line
        with special characters, it might be necessary to put
        this line in ~/.gnupg/gpg-agent.conf

       allow-loopback-pinentry

And restart gpg agent with command:

       pkill gpg-agent

  Refer to this article

  https://wiki.archlinux.org/title/GnuPG#Unattended_passphrase

2) If password was special characters, like symbols, it
   might be necessary to wrap password in 'apostrophes'
