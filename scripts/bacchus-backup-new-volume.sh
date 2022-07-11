#!/bin/bash
#
#	Helper script for multivolume tar backup to compress and encrypt each volume
#
#	Usage:
#	bacchus-backup-new-volume.sh
#
# Utilizes these environment variables:
#	BCS_DEST       - location to store final volumes
#	BCS_COMPRESDIR - Intermediate area to store compressed volume
#	BCS_COMPRESS   - Boolean enabling compression
# BCS_PASSWORD   - Password to encrypt backup archive volumes
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       bacchus does not encrypt backup

BCS_DEST=$(<"$BCS_PATHFILE")
while true; do
  availablespace=$(df -kP "$BCS_DEST" | awk '{print $4}' | tail -1)
  lowspace="$(( BCS_VOLUMESIZE * BCS_LOWDISKSPACE ))"
  printf "availablespace %s\n" "$availablespace"
  printf "lowspace       %s\n" "$lowspace"
  if [ "$availablespace" -lt "$lowspace" ]; then
    printf "LOW AVAILABLE SPACE on %s (%s < %s)\n" "$BCS_DEST" "$availablespace" "$lowspace"
    printf "Either free-up space or swap out storage device and press enter\n"
    printf "Or enter a new destination path and press enter\n"
    read newpath
    printf "\n"
    if [ -n "$newpath" ]; then
      BCS_DEST="$newpath"
      echo "$BCS_DEST" > "$BCS_PATHFILE"
    fi
  else
    break
  fi
done

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
destination="$BCS_DEST"/"$TAR_ARCHIVE"

if [ "$BCS_COMPRESS" == "on" ]; then
  if [ -n "$BCS_PASSWORD" ]; then
    destination="$BCS_COMPRESDIR"/"$TAR_ARCHIVE"
  fi
  pigz -9c "$source" > "$destination".gz
  #gzip -9c "$source" > "$destination".gz
  rm -f "$source"
  source="$destination".gz
  destination="$BCS_DEST"/"$TAR_ARCHIVE".gz
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
