#!/bin/bash
#
#	Used in multivolume tar restore to unencrypt and uncompress each volume
#
#	usage:
#	bacchus-restore-new-volume.sh sourcedir decryptdir compressdir
#
#	1 sourcedir   - Directory location of archive files
#	2 decryptdir  - Intermediate area to store unencrypted volume
#	3 compressdir - Intermediate area to store uncompressed volume

sourcedir="$1"
decryptdir="$2"
compressdir="$3"

name=$(expr "$TAR_ARCHIVE" : '\(.*\)-.*')
vol="${name:-$TAR_ARCHIVE}"-"$TAR_VOLUME"
filename="${vol##*/}"
oldname="${TAR_ARCHIVE##*/}"

echo "$filename"

source="$sourcedir"/"$filename"
if [ "$BCS_DISABLECOMPRESS" == "off" ]; then
  source="$source".gz
  rm -f "$compressdir"/"$oldname"
fi
if [ -n "$BCS_PASSWORD" ]; then
  source="$source".gpg
  rm -f "$decryptdir"/"$oldname"
fi

case "$TAR_SUBCOMMAND" in
  -x) test -r "$source" || exit 1
      ;;
  *)  exit 1
esac

if [ -n "$BCS_PASSWORD" ]; then
  if [ "$BCS_DISABLECOMPRESS" == "off" ]; then
    destination="$decryptdir"/"$filename".gz
  else
    destination="$decryptdir"/"$filename"
  fi
  echo "$BCS_PASSWORD" | gpg -qd --batch --cipher-algo AES256 --compress-algo none --passphrase-fd 0 --no-mdc-warning -o "$destination" "$source"
  source="$destination"
fi

if [ "$BCS_DISABLECOMPRESS" == "off" ]; then
  destination="$compressdir"/"$filename"
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
