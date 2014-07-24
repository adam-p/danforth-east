#!/bin/bash

rm -rf dist

grunt dist

if [[ $? == 0 ]] ; then
  \cp -rf dist/* ..
fi
