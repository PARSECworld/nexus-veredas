#!/bin/bash

VIRTUALENV=<Adicione Valor>

cd "$(dirname "$0")"
source $VIRTUALENV/bin/activate
python manage.py shell -c "exec(open('update_images.py').read())"
deactivate