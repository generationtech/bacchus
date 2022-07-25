#!/bin/bash
function Process_Volume()
{
  # Process a restore on a single archive volume
  #
  # Make sure these global variable have values before calling this function
  # BCS_COMPRESS
  # BCS_PASSWORD
  #
  # source
  #
  # Call this function with these arguements
  # $1 - current archive filename
  # $2 - decryption temporary directory
  #              (was ramdisk_size_tmpdir and BCS_DECRYPTDIR)
  # $3 - compression temporary directory
  #              (was ramdisk_size_tmpdir and BCS_COMPRESDIR)
  #
  # These variables are set in this function as globals and can
  # be accessed by the caller after completion
  #
  # dest_actual_size
  # source_actual_size

  unset source_actual_size
  unset dest_actual_size

  local destination

  if [ "$BCS_COMPRESS" == "on" ]; then
    source="$source".gz
  fi

  if [ -n "$BCS_PASSWORD" ]; then
    if [ "$BCS_COMPRESS" == "on" ]; then
      destination="$2"/"$1".gz
    else
      destination="$2"/"$1"
    fi

    if [ -z "$source_actual_size" ]; then
      source_actual_size=$(stat -c %s "$source".gpg)
    fi

    echo "$BCS_PASSWORD" | gpg -qd --batch --cipher-algo AES256 --compress-algo none --passphrase-fd 0 --no-mdc-warning -o "$destination" "$source".gpg
    source="$destination"
  fi

  if [ "$BCS_COMPRESS" == "on" ]; then
    destination="$3"/"$1"
    pigz -9cd "$source" > "$destination"
    #gzip -9cd "$source" > "$destination"

    if [ -z "$source_actual_size" ]; then
      source_actual_size=$(stat -c %s "$source")
    fi

    if [ -n "$BCS_PASSWORD" ]; then
      rm -f "$source"
    fi
    source="$destination"
  fi

  if [ -z "$source_actual_size" ]; then
    source_actual_size=$(stat -c %s "$source")
  fi
  source_actual_size=$(( source_actual_size / 1024 ))

  dest_actual_size=$(stat -c %s "$source")
  dest_actual_size=$(( dest_actual_size / 1024 ))
}
