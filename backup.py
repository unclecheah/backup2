from ftplib import FTP, error_perm
from datetime import datetime
from pathlib import Path, PurePosixPath
import os
import io
import re
import json
import hashlib
import time
import fnmatch
import shutil
import sys

CONFIGFILE = 'config.json'

config = {}

# ftp login
def ftpLogin (node):
	return FTP (
		host = config["nodes"][node]["host"],
		user = config["nodes"][node]["username"],
		passwd = config["nodes"][node]["password"]
	)


def readConfig ():
	with open(CONFIGFILE, 'r') as file:
		return json.load (file)

def readHashes (file):
	hashes = {}
	with open (file, "r", encoding="utf-8-sig") as file:
		for line in file:
			line = line.rstrip ("\r\n")
			if not line.strip (): continue

			md5, filename = line.split (" ", 1)
			hashes[filename] = md5

	return hashes

def get_file_md5(path):
	with open (path, "rb") as f:
		return hashlib.file_digest (f, "md5").hexdigest()

def get_ftp_md5(ftp_instance, remote_path):
	md5_hash = hashlib.md5()
	# Stream the file directly into the hash calculator
	ftp_instance.retrbinary(f'RETR {remote_path}', md5_hash.update)
	return md5_hash.hexdigest()

def isIgnored (path):
	# path = path.replace ('\\', '/')
	# pathParts = path.split ('/')
	# filename = os.path.basename (path)
	pathObj = Path (path)
	pathParts = pathObj.parts
	filename = pathObj.name

	for pattern in config["ignore"]:
		if pattern.endswith ('/'):
			folderName = pattern.rstrip ('/')
			if folderName in pathParts: return True
		else:
			if fnmatch.fnmatch (filename, pattern) or any (fnmatch.fnmatch (part, pattern) for part in pathParts): return True
	return False

def initHashLocal (node):
	dir = config["nodes"][node]["rootDir"]
	basePath = Path(dir)
	hashFile = f"{node}.hash"
	fDict = {}

	# get current hash file
	fPath = Path (hashFile)
	if fPath.is_file ():
		with open (hashFile, "r", encoding="utf-8") as file:
			lines = file.readlines ()

			for line in lines:
				line = line.rstrip()
				arr = line.split (" ", 1);
				fDict[arr[1]] = arr[0]


	# get hash and write to file
	with open (hashFile, "a", encoding="utf-8") as file:
		for path in sorted (basePath.rglob("*")):
			relPath = str (path.relative_to (dir))
			print (f"Processing: {path}", flush=True)
			if isIgnored (path): continue
			if str(relPath).replace ("\\", "/") in fDict:
				print (f"Skipping: {relPath}", flush=True)
				continue

			if path.is_file():
				md5 = get_file_md5 (path)
				pathStr = str(relPath).replace("\\", "/")
				fDict[pathStr] = md5
				file.write (f"{md5} {pathStr}\n")

def recurseFtp (node, cftp, baseDir, currDir = ""):
	hashFile = f"{node}.hash"
	rPath = f"{baseDir}/{currDir}".strip("/")
	fDict = {}

	# get current hash file
	fPath = Path (hashFile)
	if fPath.is_file ():
		with open (hashFile, "r", encoding="utf-8") as file:
			lines = file.readlines ()

			for line in lines:
				line = line.rstrip()
				arr = line.split (" ", 1);
				fDict[arr[1]] = arr[0]

	# get hash and write to file
	with open (hashFile, "a", encoding="utf-8") as file:
		for name, facts in cftp.mlsd (rPath):
			if name in (".", ".."): continue
			relPath = os.path.join(currDir, name).replace("\\", "/")
			print (f"Processing: {relPath}", flush=True)
			if relPath in fDict:
				print (f"Skipping: {relPath}", flush=True)
				continue

			if facts.get("type") == "dir": recurseFtp (node, cftp, baseDir, relPath)
			elif facts.get("type") == "file":
				if isIgnored (relPath): continue
				md5 = get_ftp_md5 (cftp, config["nodes"][node]["rootDir"] + "/" + relPath)
				fDict[relPath] = md5
				file.write (f"{md5} {relPath}\n")

def initHashFtp (node):
	cftp = ftpLogin (node)
	print ("Connected to ftp server")

	baseDir = config["nodes"][node]["rootDir"]
	recurseFtp (node, cftp, baseDir)

def cmpHash (node1, node2):
	first = readHashes (f"{node1}.hash")
	second = readHashes (f"{node2}.hash")

	for filename in sorted (first.keys() | second.keys()):
		if filename not in second:
			print (f"<<< {first[filename]} {filename}")
		elif filename not in first:
			print (f">>> {second[filename]} {filename}")
		elif first[filename] != second[filename]:
			print (f"xxx {filename}")

def updateHash (node, file, newHash):
	path = Path (f"{node}.hash")
	lines = (
		path.read_text (encoding="utf-8-sig").splitlines ()
		if path.exists ()
		else []
	)
	found = False

	for index, line in enumerate (lines):
		oldHash, separator, storedFilename = line.partition (" ")

		if separator and storedFilename == file:
			lines[index] = f"{newHash} {storedFilename}"
			found = True

	if not found: lines.append (f"{newHash} {file}")

	path.write_text ("\n".join (lines) + "\n", encoding="utf-8")

def updateFile (srcNode, dstNode, file):
	src = f"{config['nodes'][srcNode]['rootDir']}/{file}"
	dst = f"{config['nodes'][dstNode]['rootDir']}/{file}"

	destination = Path (dst)
	destination.parent.mkdir (parents = True, exist_ok = True)

	shutil.copy2 (src, destination)
	hash = get_file_md5 (dst)
	updateHash (dstNode, file, hash)

def updateFtp (ftpC, srcNode, dstNode, file):
	src = f"{config['nodes'][srcNode]['rootDir']}/{file}"
	dst = f"{config['nodes'][dstNode]['rootDir']}/{file}"

	destination = PurePosixPath (str (dst))
	orgDir = ftpC.pwd ()

	with open (src, "rb") as source:
		for folder in destination.parent.parts:
			if folder in ("/", "."): continue
			try:
				ftpC.cwd (folder)
			except error_perm:
				ftpC.mkd (folder)
				ftpC.cwd (folder)

		ftpC.storbinary (f"STOR {destination.name}", source, blocksize = 64 * 1024)

	hash = get_ftp_md5 (ftpC, destination.name)
	updateHash (dstNode, file, hash)
	ftpC.cwd (orgDir)

def bulkUpdFile (srcNode, dstNode):
	first = readHashes (f"{srcNode}.hash")
	second = readHashes (f"{dstNode}.hash")
	toUpd = []

	for filename in sorted (first.keys() | second.keys()):
		if filename not in second:
			print (f"Identified {filename}")
			toUpd.append (filename)
		elif filename not in first:
			print (f">>> {second[filename]} {filename}")
		elif first[filename] != second[filename]:
			print (f"Identified {filename}")
			toUpd.append (filename)
	
	# print (toUpd)
	for item in toUpd:
		print (f"Updating {item}")
		updateFile (srcNode, dstNode, item)

def bulkUpdFtp (ftpC, srcNode, dstNode):
	first = readHashes (f"{srcNode}.hash")
	second = readHashes (f"{dstNode}.hash")
	toUpd = []

	for filename in sorted (first.keys() | second.keys()):
		if filename not in second:
			print (f"Identified {filename}")
			toUpd.append (filename)
		elif filename not in first:
			print (f">>> {second[filename]} {filename}")
		elif first[filename] != second[filename]:
			print (f"Identified {filename}")
			toUpd.append (filename)
	
	# print (toUpd)
	for item in toUpd:
		print (f"Updating {item}")
		updateFtp (ftpC, srcNode, dstNode, item)

def msg ():
	print (
		"Usage: backup.py compare <src> <dst>\n"
		"       backup.py update <src> dst>\n"
	)

def main ():
	global config

	if len(sys.argv) != 4:
		msg ()
		return

	config = readConfig()
	opn = sys.argv[1]
	src = sys.argv[2]
	dst = sys.argv[3]

	if opn not in ["compare", "update"]:
		print ("operation not recognized")
		return

	if (src not in config["nodes"]):
		print ("source node not found")
		return
	if (dst not in config["nodes"]):
		print ("destination node not found")
		return

	srcType = config["nodes"][src]["type"]
	dstType = config["nodes"][dst]["type"]

	if srcType != "local":
		print ("source must be local")
		return

	if opn == "compare":
		cmpHash (src, dst)
		return

	if opn == "update":
		if dstType == "local":
			bulkUpdFile (src, dst)
		elif dstType == "ftps":
			ftpC = ftpLogin (dst)
			bulkUpdFtp (ftpC, src, dst)




def tMoveCursor():
	for i in range(101):
		print(f"\rProgress: {i}%", end="", flush=True)
		time.sleep(0.1)

def tWriteFile():
	with open("output.txt", "w", encoding="utf-8") as file:
		for i in range(101):
			file.write (f"\rPreamble: {i}")
			time.sleep (0.1)

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

def tUpdateHash ():
	# updateHash ("test", "musescore/Beloved.mscz", "414f86225154dd5e25974ff03533zzzz")
	updateHash ("test", "musescore/Beloved2.mscz", "414f86225154dd5e25974ff03533zzzz")

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

def tStrInArr (config):
	if "router" in config["destinations"]: print (config["destinations"]["router"]["rootDir"])


# print (get_file_md5("c:/data/music/choir/recordings/Misc/Signed By Ashes.m4a"))

# print (get_ftp_md5 (ftp, "/choir.unclecheah.com/data/music/recordings/Misc/Goodness Of God.mp3"));
# print (get_ftp_md5 (ftp, "/choir.unclecheah.com/data/music/recordings/Misc/This Is The Day.m4a"));
# print (get_ftp_md5 (ftp, "/choir.unclecheah.com/data/music/recordings/Misc/The See Of Peter.m4a"));
# print (get_ftp_md5 (ftp, "/choir.unclecheah.com/data/music/recordings/Misc/Signed By Ashes.m4a"));

# print (get_file_md5("c:/data/music/choir/recordings/Misc/Signed By Ashes.m4a"))

# print (get_ftp_md5 (ftp, "/choir.unclecheah.com/data/music/recordings/Misc/Goodness Of God.mp3"));
# print (get_ftp_md5 (ftp, "/choir.unclecheah.com/data/music/recordings/Misc/This Is The Day.m4a"));
# print (get_ftp_md5 (ftp, "/choir.unclecheah.com/data/music/recordings/Misc/The See Of Peter.m4a"));
# print (get_ftp_md5 (ftp, "/choir.unclecheah.com/data/music/recordings/Misc/Signed By Ashes.m4a"));

# config = readConfig()
# ftpC = ftpLogin ('web2')

# tMoveCursor()
# tWriteFile()
# tRecurseDir()
# tRecurseFtp (ftp, baseDir="/test.unclecheah.com/music")
# tRepHash("File 2", "someHash2")
# tReadFileByLine()
# tArraySplit()
# tFile2Hash()
# tStrInArr(config)
# tUpdateHash()

# initHashLocal("shock2")
# initHashFtp("web2")
# cmpHash ("shock2", "router2")
# updateFile ("shock2", "router2", "scores/SPG/A Banquet Is Prepared [SPG001].pdf")
# updateFtp (ftpC, "shock2", "web2", "scores/SPG/A Banquet Is Prepared [SPG001].pdf")
# bulkUpdFile ("shock2", "router2")
# bulkUpdFtp (ftpC, "shock2", "web2")

if __name__ == "__main__": main ()
