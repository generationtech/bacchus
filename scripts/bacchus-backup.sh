#!/bin/bash
#
#	Bacchus backup script
#
#	Creates multi-volume backups, first compressing and then encrypting.
#	Allows for creating smaller backups with privacy while allowing
# for partial recovery should any individual incremental archive
# file be damaged.
#
# Other similar solutions using encryption result in total data
# loss past failed incremental archive file.
#
#	Usage:
#	bacchus-backup.sh
#
# Utilizes these environment variables:
#	BCS_SOURCE     - Directory to backup
#	BCS_DEST       - directory location of archive files
#	BCS_BASENAME   - Base filename for backup archive, appending
#                  incremental backup volume number
#	BCS_TARDIR     - Intermediate area for tar
#	BCS_COMPRESDIR - Intermediate area to store compressed volume
#	BCS_VOLUMESIZE - Size of each volume in kB
# BCS_PASSWORD   - Password to encrypt backup archive volumes
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       bacchus does not encrypt backup

scriptdir=$(dirname "$_")

Cleanup()
{
  if [[ "$BCS_TMPFILE" == *"tmp"* ]]; then
    rm -rf "$BCS_TMPFILE"
  fi
}

BCS_TMPFILE=$(mktemp -u /tmp/baccus-XXXXXX)
trap Cleanup EXIT

if [ "$BCS_COMPRESS" == "off" ] && [ -z "$BCS_PASSWORD" ]; then
  BCS_TARDIR="$BCS_DEST"
fi

if [ "$BCS_VERBOSETAR" == "on" ]; then
  tarargs='-cpMv'
else
  tarargs='-cpM'
fi

tar "$tarargs" --format=posix --sort=name --new-volume-script "$scriptdir/bacchus-backup-new-volume.sh" -L "$BCS_VOLUMESIZE" --volno-file "$BCS_TMPFILE" -f "$BCS_TARDIR"/"$BCS_BASENAME".tar $BCS_SOURCE

# Setup tar variables to call new-volume script for handling last (or possibly only) archive volume
vol=$(cat "$BCS_TMPFILE")
case "$vol" in
  1)  export TAR_ARCHIVE="$BCS_TARDIR"/"$BCS_BASENAME".tar
      ;;
  *)  export TAR_ARCHIVE="$BCS_TARDIR"/"$BCS_BASENAME".tar-"$vol"
esac

export TAR_VOLUME=$(expr "$vol" + 1)
export TAR_SUBCOMMAND="-c"
export TAR_FD="none"
"$scriptdir"/bacchus-backup-new-volume.sh "$BCS_DEST" "$BCS_COMPRESDIR"
printf '\n'
