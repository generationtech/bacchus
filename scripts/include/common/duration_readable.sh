#!/bin/bash
function Duration_Readable()
{
  # Call this function with one argument
  # $1 - time respresented as total number of seconds

  local string_date
  local remainder
  local days
  local hours
  local minutes

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
  remainder=$(( remainder - (hours*3600) ))

  minutes=$(( remainder/60 ))
  if [ $minutes -gt 0 ]; then
    if [ -n "$string_date" ]; then
      string_date+=":"
    fi
    string_date+="${minutes}m"
  fi
  remainder=$(( remainder - (minutes*60) ))

  if [ $remainder -gt 0 ]; then
    if [ -n "$string_date" ]; then
      string_date+=":"
    fi
    string_date+="${remainder}s"
  fi

  printf "%s" "$string_date"
}
