from ftplib import FTP
from datetime import datetime
from pathlib import Path
import os
import io
import re
import json
import hashlib
import time

config = {}
config['ftp'] = {}
config['ftp']['site'] = "unclecheah.com"
config['ftp']['user'] = "unclecheah@unclecheah.com"
config['ftp']['pwd'] = "uncle1218Pass"


def get_file_md5(path):
	with open (path, "rb") as f:
		return hashlib.file_digest (f, "md5").hexdigest()


def get_ftp_md5(ftp_instance, remote_path):
	md5_hash = hashlib.md5()
	# Stream the file directly into the hash calculator
	ftp_instance.retrbinary(f'RETR {remote_path}', md5_hash.update)
	return md5_hash.hexdigest()


# login
ftp = FTP (
	host = config['ftp']['site'],
	user = config['ftp']['user'],
	passwd = config['ftp']['pwd']
)


def tMoveCursor():
	for i in range(101):
		print(f"\rProgress: {i}%", end="", flush=True)
		time.sleep(0.1)

def tWriteFile():
	with open("output.txt", "w", encoding="utf-8") as file:
		for i in range(101):
			file.write (f"\rPreamble: {i}")
			time.sleep (0.1)

def tReadJson():
	with open('config.json', 'r') as file:
		config = json.load (file)
		print (config['destinations']['webhost']['type'])

def tRecurseDir():
	basePath = Path("c:/data/tmp/music")

	for path in sorted (basePath.rglob("*")):
		if path.is_file():
			relPath = path.relative_to (basePath)
			print(relPath)

def tRecurseFtp(cftp, baseDir, currDir = ""):
	rPath = f"{baseDir}/{currDir}".strip("/")

	for name, facts in cftp.mlsd (rPath):
		if name in (".", ".."): continue
		relPath = os.path.join(currDir, name).replace("\\", "/")

		if facts.get("type") == "dir": tRecurseFtp (cftp, baseDir, relPath)
		elif facts.get("type") == "file": print (relPath)

def tRepHash(sSearch, newHash):
	with open ("hashLocal.txt", 'r') as file:
		fContents = file.read()

		pattern = r'^\s*\S+(.*' + re.escape(sSearch) + r')'
		replacement = re.escape(newHash) + r'\1'
		updContents = re.sub(pattern, replacement, fContents, flags=re.MULTILINE)
		
		with open ("hashLocal.txt", 'w') as file: file.write (updContents)

def tReadFileByLine ():
	with open ("hashLocal.txt", 'r') as file:
		lines = file.readlines ()

	for line in lines:
		print (line)

def tArraySplit ():
	arr = [];
	arr.append ("012345 File 3")
	arr.append ("285721 File 2")
	arr.append ("396210 File 1")

	master = [];
	for item in arr:
		# sp = item.split (" ", 1)
		# print (sp)
		master.append (item.split (" ", 1))

	master.sort (key=lambda x: x[1])
	print (master)

def tFile2Hash ():
	arr = [];
	arr.append ("012345 File 1")
	arr.append ("285721 File 2")
	arr.append ("396210 File 3")

	master = [];
	for item in arr:
		# sp = item.split (" ", 1)
		# print (sp)
		master.append (item.split (" ", 1))

	for hash, fName in master:
		if fName == "File 2": print (hash)

	return None


# tMoveCursor()
# tWriteFile()
# tReadJson()
# tRecurseDir()
# tRecurseFtp (ftp, baseDir="/test.unclecheah.com/music")
# tRepHash("File 2", "someHash2")
# tReadFileByLine()
tArraySplit()
# tFile2Hash()

# print (get_file_md5("c:/data/music/choir/recordings/Misc/Signed By Ashes.m4a"))

# print (get_ftp_md5 (ftp, "/choir.unclecheah.com/data/music/recordings/Misc/Goodness Of God.mp3"));
# print (get_ftp_md5 (ftp, "/choir.unclecheah.com/data/music/recordings/Misc/This Is The Day.m4a"));
# print (get_ftp_md5 (ftp, "/choir.unclecheah.com/data/music/recordings/Misc/The See Of Peter.m4a"));
# print (get_ftp_md5 (ftp, "/choir.unclecheah.com/data/music/recordings/Misc/Signed By Ashes.m4a"));

