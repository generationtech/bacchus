#! /bin/bash
#
#	Used in multivolume tar restore to unencrypt and uncompress each volume
#
#	usage:
#	bacchus-restore-new-volume.sh sourcedir compressdir encryptdir
#
#	1 sourcedir   - Directory location of archive files
#	2 compressdir - Intermediate area to store uncompressed volume
#	3 encryptdir  - Intermediate area to store unencrypted volume

sourcedir="$1"
compressdir="$2"
encryptdir="$3"

name=$(expr "$TAR_ARCHIVE" : '\(.*\)-.*')
vol="${name:-$TAR_ARCHIVE}"-"$TAR_VOLUME"
filename="${vol##*/}"
oldname="${TAR_ARCHIVE##*/}"

echo "$filename"

case "$TAR_SUBCOMMAND" in
-x)       test -r "$sourcedir"/"$filename".gz.gpg || exit 1
          ;;
*)        exit 1
esac

rm "$compressdir"/"$oldname"

if [ -n "$BCS_PASSWORD" ]; then
  echo "$BCS_PASSWORD" | gpg --pinentry-mode loopback -qd --cipher-algo AES256 --compress-algo none --passphrase-fd 0 --no-mdc-warning -o "$encryptdir"/"$filename".gz "$sourcedir"/"$filename".gz.gpg
fi

gzip -9cd "$encryptdir"/"$filename".gz > "$compressdir"/"$filename"

rm -f "$encryptdir"/"$filename".gz

case "$TAR_FD" in
none)    exit 0
         ;;
*)       echo "${name:-$TAR_ARCHIVE}"-"$TAR_VOLUME" >&"$TAR_FD"
esac

exit 0
