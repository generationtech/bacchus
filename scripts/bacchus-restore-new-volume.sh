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

case "$TAR_SUBCOMMAND" in
  -x) if [ -n "$BCS_PASSWORD" ]; then
        test -r "$sourcedir"/"$filename".gz.gpg || exit 1
      else
        test -r "$sourcedir"/"$filename".gz || exit 1
      fi
      ;;
  *)  exit 1
esac

rm "$compressdir"/"$oldname"

if [ -n "$BCS_PASSWORD" ]; then
  echo "$BCS_PASSWORD" | gpg -qd --batch --cipher-algo AES256 --compress-algo none --passphrase-fd 0 --no-mdc-warning -o "$decryptdir"/"$filename".gz "$sourcedir"/"$filename".gz.gpg
  compresssource="$decryptdir"
else
  compresssource="$sourcedir"
fi

pigz -9cd "$compresssource"/"$filename".gz > "$compressdir"/"$filename"
#gzip -9cd "$compresssource"/"$filename".gz > "$compressdir"/"$filename"
if [ -n "$BCS_PASSWORD" ]; then
  rm -f "$decryptdir"/"$filename".gz
fi

case "$TAR_FD" in
  none) exit 0
        ;;
  *)    echo "${name:-$TAR_ARCHIVE}"-"$TAR_VOLUME" >&"$TAR_FD"
esac

exit 0
