#!/bin/sh
# Пересеять демо-мир DEMO1 из seed/ — после обновления наборов.
# Удаляет его жителей из базы и с диска; при следующем старте сервера seedDemo() засеет заново.
cd "$(dirname "$0")/.."
DATA="${DATA_DIR:-./data}"
node --no-warnings -e "
const {DatabaseSync}=require('node:sqlite');
const db=new DatabaseSync('$DATA/kidstv.db');
const n=db.prepare('DELETE FROM monsters WHERE code = ?').run('DEMO1').changes;
console.log('удалено жителей DEMO1:', n);"
rm -rf "$DATA/monsters/DEMO1"
echo "теперь перезапусти сервер: node --no-warnings server.js"
