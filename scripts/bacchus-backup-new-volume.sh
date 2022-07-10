#!/bin/bash
#
#	Used in multivolume tar backup to compress and encrypt each volume
#
#	usage:
#	bacchus-backup-new-volume.sh destdir compressdir
#
#	1 destdir  - location to store final volumes
#	2 compressdir - Intermediate area to store compressed volume

destdir="$1"
compressdir="$2"

tararchivedir=$(dirname "$TAR_ARCHIVE")
TAR_ARCHIVE=$(basename "$TAR_ARCHIVE")
name=$(expr "$TAR_ARCHIVE" : '\(.*\)-.*')
vol=${name:-"$TAR_ARCHIVE"}-"$TAR_VOLUME"

printf '%s\n' "$TAR_ARCHIVE"

case "$TAR_SUBCOMMAND" in
  -c)       ;;
  -d|-x|-t) test -r "${name:-$TAR_ARCHIVE}"-"$TAR_VOLUME" || exit 1
            ;;
  *)        exit 1
esac

source="$tararchivedir"/"$TAR_ARCHIVE"
destination="$destdir"/"$TAR_ARCHIVE"

if [ "$BCS_DISABLECOMPRESS" == "off" ]; then
  if [ -n "$BCS_PASSWORD" ]; then
    destination="$compressdir"/"$TAR_ARCHIVE"
  fi
  pigz -9c "$source" > "$destination".gz
  #gzip -9c "$source" > "$destination".gz
  rm -f "$source"
  source="$destination".gz
  destination="$destdir"/"$TAR_ARCHIVE".gz
fi

if [ -n "$BCS_PASSWORD" ]; then
  echo "$BCS_PASSWORD" | gpg -qc --cipher-algo AES256 --compress-algo none --batch --passphrase-fd 0 -o "$destination".gpg "$source"
  rm -f "$source"
fi

tarnew="$tararchivedir"/"$vol"
case "$TAR_FD" in
  none) exit 0
        ;;
  *)    echo "$tarnew" >&"$TAR_FD"
esac
