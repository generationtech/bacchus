#!/bin/bash
#
#	Helper script for multivolume tar restore to unencrypt and uncompress each volume
#
#	Usage:
#	bacchus-restore-new-volume.sh
#
# Utilizes these environment variables:
#	BCS_SOURCE     - Directory location of archive files
#	BCS_DECRYPTDIR - Intermediate area to store unencrypted volume
#	BCS_COMPRESDIR - Intermediate area to store uncompressed volume
# BCS_PASSWORD   - Password to encrypt backup archive volumes
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       Bacchus does not unencrypt backup, and operation will fail if
#       archive was backed up as encrypted

name=$(expr "$TAR_ARCHIVE" : '\(.*\)-.*')
vol="${name:-$TAR_ARCHIVE}"-"$TAR_VOLUME"
filename="${vol##*/}"
oldname="${TAR_ARCHIVE##*/}"

echo "$filename"

source="$BCS_SOURCE"/"$filename"
if [ "$BCS_COMPRESS" == "on" ]; then
  source="$source".gz
  rm -f "$BCS_COMPRESDIR"/"$oldname"
fi
if [ -n "$BCS_PASSWORD" ]; then
  source="$source".gpg
  rm -f "$BCS_DECRYPTDIR"/"$oldname"
fi

case "$TAR_SUBCOMMAND" in
  -x) test -r "$source" || exit 1
      ;;
  *)  exit 1
esac

if [ -n "$BCS_PASSWORD" ]; then
  if [ "$BCS_COMPRESS" == "on" ]; then
    destination="$BCS_DECRYPTDIR"/"$filename".gz
  else
    destination="$BCS_DECRYPTDIR"/"$filename"
  fi
  echo "$BCS_PASSWORD" | gpg -qd --batch --cipher-algo AES256 --compress-algo none --passphrase-fd 0 --no-mdc-warning -o "$destination" "$source"
  source="$destination"
fi

if [ "$BCS_COMPRESS" == "on" ]; then
  destination="$BCS_COMPRESDIR"/"$filename"
  pigz -9cd "$source" > "$destination"
  #gzip -9cd "$source" > "$destination"
  if [ -n "$BCS_PASSWORD" ]; then
    rm -f "$source"
  fi
  source="$destination"
fi

case "$TAR_FD" in
  none) exit 0
        ;;
  *)    echo "${name:-$TAR_ARCHIVE}"-"$TAR_VOLUME" >&"$TAR_FD"
esac

exit 0
