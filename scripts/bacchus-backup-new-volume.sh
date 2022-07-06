#! /bin/bash
#
#	Used in multivolume tar backup to compress and encrypt each volume
#
#	usage:
#	bacchus-backup-new-volume.sh compressdir encryptdir
#
#	1 compressdir - Intermediate area to store compressed volume
#	2 encryptdir  - location to store final volumes

compressdir="$1"
encryptdir="$2"

tardir=$(dirname "$TAR_ARCHIVE")
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

pigz -9c "$tardir"/"$TAR_ARCHIVE" > "$compressdir"/"$TAR_ARCHIVE".gz
#gzip -9c "$tardir"/"$TAR_ARCHIVE" > "$compressdir"/"$TAR_ARCHIVE".gz

if [ -n "$BCS_PASSWORD" ]; then
  echo "$BCS_PASSWORD" | gpg -qc --cipher-algo AES256 --compress-algo none --batch --passphrase-fd 0 -o "$encryptdir"/"$TAR_ARCHIVE".gz.gpg "$compressdir"/"$TAR_ARCHIVE".gz

  rm -f "$compressdir"/"$TAR_ARCHIVE".gz
fi

rm "$tardir"/"$TAR_ARCHIVE"

tarnew="$tardir"/"$vol"
case "$TAR_FD" in
none)    exit 0
         ;;
*)       echo "$tarnew" >&"$TAR_FD"
esac
