#!/bin/bash
#
#	Helper script for multivolume tar backup to compress and encrypt each volume
#
#	Usage:
#	bacchus-backup-new-volume.sh
#
# Utilizes these environment variables:
#	BCS_DATAFILE   - File used to save/retrieve current destination location
#	BCS_COMPRESDIR - Intermediate area to store compressed volume
#	BCS_COMPRESS   - Boolean enabling compression
# BCS_PASSWORD   - Password to encrypt backup archive volumes
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       bacchus does not encrypt backup

Duration_Readable()
{
  string_date=""

  days=$(( $1/3600/24 ))
  if [ $days -gt 0 ]; then
    string_date+="${days}d"
  fi
  remainder=$(( $1 - (days*3600*24) ))

  hours=$(( remainder/3600 ))
  if [ $hours -gt 0 ]; then
    if [ -n "$string_date" ]; then
      string_date+=":"
    fi
    string_date+="${hours}h"
  fi
  remainder=$(( remainder - ($hours*3600) ))

  minutes=$(( remainder/60 ))
  if [ $minutes -gt 0 ]; then
    if [ -n "$string_date" ]; then
      string_date+=":"
    fi
    string_date+="${minutes}m"
  fi
  remainder=$(( remainder - ($minutes*60) ))

  if [ $remainder -gt 0 ]; then
    if [ -n "$string_date" ]; then
      string_date+=":"
    fi
    string_date+="${remainder}s"
  fi

  printf "%s" "$string_date"
}

# Pull current runtime data from persistence file
runtime_data=$(<"$BCS_DATAFILE")
bcs_dest=$(echo "$runtime_data"            | jq -r '.bcs_dest')
start_timestamp=$(echo "$runtime_data"     | jq -r '.start_timestamp')
last_timestamp=$(echo "$runtime_data"      | jq -r '.last_timestamp')
source_size_total=$(echo "$runtime_data"   | jq -r '.source_size_total')
source_size_running=$(echo "$runtime_data" | jq -r '.source_size_running')
archive_volumes=$(echo "$runtime_data"     | jq -r '.archive_volumes')

# Compute new archive volume details
tararchivedir=$(dirname "$TAR_ARCHIVE")
TAR_ARCHIVE=$(basename "$TAR_ARCHIVE")
name=$(expr "$TAR_ARCHIVE" : '\(.*\)-.*')
vol=${name:-"$TAR_ARCHIVE"}-"$TAR_VOLUME"

# Make sure running correct tar subcommand
case "$TAR_SUBCOMMAND" in
  -c)       ;;
  -d|-x|-t) test -r "${name:-$TAR_ARCHIVE}"-"$TAR_VOLUME" || exit 1
            ;;
  *)        exit 1
esac

# Ensure sufficient available free space on target for this archive volume
while true; do
  availablespace=$(df -kP "$bcs_dest" | awk '{print $4}' | tail -1)
  lowspace="$(( BCS_VOLUMESIZE * BCS_LOWDISKSPACE ))"
  if [ "$availablespace" -lt "$lowspace" ]; then
    printf "\nLOW AVAILABLE SPACE on %s (%s < %s)\n" "$bcs_dest" "$availablespace" "$lowspace"
    printf "Either free-up space or swap out storage device and press enter\n"
    printf "Or enter a new destination path and press enter\n"
    read -r newpath
    printf "\n"
    if [ -n "$newpath" ]; then
      bcs_dest="$newpath"
    fi
  else
    break
  fi
done

# Source and Destination variables flow through following sections
source="$tararchivedir"/"$TAR_ARCHIVE"
destination="$bcs_dest"/"$TAR_ARCHIVE"

archive_source_size=$(stat -c %s "$source")
archive_source_size_scaled=$(( archive_source_size / 1024 ))
source_size_running=$(( $source_size_running + $archive_source_size_scaled ))

# Commpression if enabled
if [ "$BCS_COMPRESS" == "on" ]; then
  if [ -n "$BCS_PASSWORD" ]; then
    destination="$BCS_COMPRESDIR"/"$TAR_ARCHIVE"
  fi
  pigz -9c "$source" > "$destination".gz
  #gzip -9c "$source" > "$destination".gz
  rm -f "$source"
  source="$destination".gz
  destination="$bcs_dest"/"$TAR_ARCHIVE".gz
fi

# Encryption if enabled
if [ -n "$BCS_PASSWORD" ]; then
  destination="$destination".gpg
  echo "$BCS_PASSWORD" | gpg -qc --cipher-algo AES256 --compress-algo none --batch --passphrase-fd 0 -o "$destination" "$source"
  rm -f "$source"
fi

# Compute & output incremntal statistics
archive_max_name=$(( ${#BCS_BASENAME} + `expr length "$archive_volumes"` + 5 ))
archive_max_num=$(( `expr length "$archive_volumes"` + 1 ))

source_size_text=`expr length "$source_size_total"`
max_source_size_text=$(( source_size_text + (source_size_text / 3) + 9 ))
source_size_running_text=`printf "%'.0f" $source_size_running`

dest_size=$(du -c "$bcs_dest"/"$BCS_BASENAME"* | tail -1 | awk '{ print $1 }')
dest_size_text=`printf "%'.0f" $dest_size`

completion_timestamp="$(date +%s)"
diff_time=$(( completion_timestamp - start_timestamp ))
avg_archive_time=$(( ( diff_time / (TAR_VOLUME - 1) ) ))
remain_time=$(( (avg_archive_time * (archive_volumes - TAR_VOLUME + 1) ) ))

printf "\
%-${archive_max_name}s \
%${archive_max_num}s \
%6s  \
%-18s \
%-18s \
%-10s \
%-10s \
%-11s \
%-${max_source_size_text}s \
%-${max_source_size_text}s \
%(%m-%d-%Y %H:%M:%S)T\n" \
    "$TAR_ARCHIVE" \
    "/$archive_volumes" \
    "($(( ((TAR_VOLUME - 1) * 100) / archive_volumes ))%)" \
    "remain($( Duration_Readable $remain_time ))" \
    "elapsed($( Duration_Readable $diff_time ))" \
    "last($( Duration_Readable $(( $completion_timestamp - $last_timestamp )) ))" \
    "avg($( Duration_Readable $avg_archive_time ))" \
    "compr($(( 100 - ( ( dest_size * 100) / source_size_running ) ))%)" \
    "source(${source_size_running_text}k)" \
    "dest(${dest_size_text}k)" \
    "$completion_timestamp"

# Update tar archive volume # counter
tarnew="$tararchivedir"/"$vol"
case "$TAR_FD" in
  none) completion_timestamp="$(date +%s)"
        diff_time=$(( completion_timestamp - start_timestamp ))
        avg_archive_time=$(( ( diff_time / (TAR_VOLUME - 1) ) ))

        source_size_running_text=`printf "%'.0f" $source_size_running`

        dest_size=$(du -c "$bcs_dest"/"$BCS_BASENAME"* | tail -1 | awk '{ print $1 }')
        dest_size_text=`printf "%'.0f" $dest_size`

        comp_ratio=$(( 100 - ( ( dest_size * 100) / source_size_running ) ))

        printf '\nBACKUP OPERATION COMPLETE\n'
        printf 'Total runtime:                 %s\n' "$( Duration_Readable $diff_time )"
        printf 'Average time per archive file: %s\n' "$( Duration_Readable $avg_archive_time )"
        printf 'Number of archive files:       %s\n' "$(( TAR_VOLUME - 1 ))"
        printf 'Total space backed up:         %sk\n' "$source_size_running_text"
        printf 'Total space on destination:    %sk\n' "$dest_size_text"
        printf 'Overall compression ratio:     %s%%\n' "$comp_ratio"

        exit 0
        ;;

  *)    echo "$tarnew" >&"$TAR_FD"
esac

# Update runtime data to persistence file
last_timestamp="$(date +%s)"
runtime_data=$(jo bcs_dest="$bcs_dest" \
                  start_timestamp="$start_timestamp" \
                  last_timestamp="$last_timestamp" \
                  source_size_total=$source_size_total \
                  source_size_running=$source_size_running \
                  archive_volumes=$archive_volumes)
echo "$runtime_data" > "$BCS_DATAFILE"
