'''
A script to parse the 4KB configration space dump of a PCIe device.
User need to first obtain a dump of the 4KB configuration space.
And then create a yaml file to specify the registers of interest.
The script will use the yaml to search and parse the PCIe config space.

Copyright (c) 2023-2024 Ming Shao (smwikipedia@163.com)

MIT License

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

'''
import sys
import argparse
import re
import yaml
import time
from pathlib import Path

Config4K = []

'''
Assuming below dump line format:

2023-10-12 09:10:54	  00000040: 00 00 00 00 00 00 00 00-00 00 00 00 00 00 00 00  *................*

The offset and values are mandatory.
Each line must contain 16 bytes of config space content.
The total dump must contain 0xFFF+1 bytes.
The timestamp is insignificant.

'''
reLine = r"([a-fA-F0-9]{8})\:((\s*[a-fA-F0-9]{2})+\-([a-fA-F0-9]{2}\s*)+)"
reByte = r"(\s[a-fA-F0-9]{2})"


def Get4KDump():
    if (args.raw):
        print("Raw dump:")
    hexDumpFile = args.dump
    f = open(hexDumpFile, "r")
    line = f.readline()
    collect = False
    expectedOffset = 0
    while (line):
        m = re.search(reLine, line)
        if (m):
            offset = int(m.groups()[0], 16)
            if (offset == 0):
                collect = True
            if (collect):
                if (offset != expectedOffset):
                    print(f"Bad dump at {offset}, expected {expectedOffset}")
                    sys.exit(1)
                dumpLine = m.groups()[1]
                if (args.raw):
                    print(f"{hex(offset).upper()[2:]:0>8}: {dumpLine}")
                dumpLine = dumpLine.replace("-", " ")
                dumpBytes = re.findall(reByte, dumpLine)
                Config4K.extend([int(x, 16) for x in dumpBytes])
                expectedOffset += 16
            if (offset == 0xFF0):
                collect = False
        line = f.readline()
    print()
    return

def GetHeaderType():
    headerTypeReg = ConfigRead(0xE, 1)
    headerLayout = GetBitField(headerTypeReg, 0, 6)
    if (headerLayout == 0):
        return 0
    if (headerLayout == 1):
        return 1
    print (f"Reserved header layout value: {headerLayout}")
    sys.exit(1)


def ConfigRead(offset, regWidth):  # regWidth in byte
    if (not regWidth in [1, 2, 3, 4]):
        print("Bad register width!")
        sys.exit(1)
    Value = 0
    for i in range(regWidth):
        # Little endian
        Value += (Config4K[offset + i] * (1 << (8 * i)))
    return Value


def GetBitField(data, bitLow, bitHigh):
    mask1 = ((1 << bitHigh) - 1 + (1 << bitHigh))
    mask2 = (1 << bitLow) - 1
    mask = mask1 - mask2
    return ((data & mask) >> bitLow)


def CapRecognized(capsDB, capId):
    capIds = capsDB.keys()
    return capId in capIds


def ParseSinglePciPcieCap(capsDB, capId, capOffset):
    if (capId not in capsDB.keys()):
        return
    # If use yaml list, we can't get the cap object so easily as below
    capObj = capsDB[capId]
    capObj["Offset"] = f"0x{hex(capOffset)[2:].upper()}"
    regCapOffsets = capObj.keys()
    for regCapOffset in regCapOffsets:
        if (type(regCapOffset) is not int): # Name, Width
            continue
        regObj = capObj[regCapOffset]
        regWidthNum = capObj[regCapOffset]["Width"]
        valWidth = 2 * regWidthNum  # a byte has two hex digit
        regOffset = capOffset + regCapOffset
        regVal = ConfigRead(regOffset, regWidthNum)
        regObj["Value"] = f"0x{hex(regVal)[2:].upper():0>{valWidth}}"
        # If register fields are specified, just continue to parse it.
        for fieldKey in regObj.keys():
            if (type(fieldKey) is not int):
                continue
            fieldObj = regObj[fieldKey]
            lowBitNum = fieldKey
            hiBitNum = fieldObj["HiBit"]
            fieldVal = GetBitField(regVal, lowBitNum, hiBitNum)
            fieldValWidth = (hiBitNum - lowBitNum + 1 + 3) // 4  # integer division
            fieldObj["Value"] = f"0x{hex(fieldVal)[2:].upper():0>{fieldValWidth}}"

def ParsePciCap(capsDB):
    '''
    Begin from offset 0x34, a 1-byte link
    [7:0] Extended Cap ID
    [15:8] Next Cap Pointer
    '''
    print("PCI Capabilities:")
    print("-----------------")
    capOffset = ConfigRead(0x34, 1)
    while (capOffset):
        capId = ConfigRead(capOffset, 1)
        print(f"  {hex(capId).upper()[2:]:0>2}h @ {hex(capOffset).upper()[2:]:0>2}h")
        ParseSinglePciPcieCap(capsDB, capId, capOffset)
        capOffset = ConfigRead(capOffset + 1, 1)
    print()
    return


def ParsePcieExtendedCap(extCapsDB):
    '''
    Begin from offset 0x100
    [15:0] Extended Cap ID
    [19:16] Cap Ver.
    [31: 20] Next Cap Offset
    '''
    print("PCIe Extended Capabilities:")
    print("---------------------------")
    capOffset = 0x100
    while capOffset:
        data = ConfigRead(capOffset, 4)
        capId = GetBitField(data, 0, 15)
        capVer = GetBitField(data, 16, 19)
        print(f"  {hex(capId).upper()[2:]:0>4}h of v{hex(capVer).upper()[2:]} @ {hex(capOffset).upper()[2:]:0>3}h")
        ParseSinglePciPcieCap(extCapsDB, capId, capOffset)
        capOffset = GetBitField(data, 20, 31)
    print()
    return


def LoadRegTemplate(capTemplateFile):
    with open(capTemplateFile, "r") as f:
        try:
            capsDB = yaml.safe_load(f)
        except yaml.YAMLError as ex:
            print(ex)
            sys.exit(1)
    return capsDB


def DumpResultYaml(yamlDB, dumpFileName):
    timestamp = time.strftime("_%Y%m%d-%H%M%S")
    dumpFileName = "Result." + dumpFileName + timestamp + ".yml"
    with open(dumpFileName, 'w', encoding='utf8') as f:
        yaml.dump(yamlDB, f)


def ParseConfig():
    if (args.header):
        headersDB = LoadRegTemplate("ConfigDB/Headers.yml")
        ParseHeader(headersDB)
        DumpResultYaml(headersDB, "Header")
        PrintHeader01(headersDB)
    if (args.cap):
        capsDB = LoadRegTemplate("ConfigDB/Caps.yml")
        ParsePciCap(capsDB)
        DumpResultYaml(capsDB, "Caps")
        PrintCaps(capsDB)
    if (args.extcap):
        extCapsDB = LoadRegTemplate ("ConfigDB/ExtCaps.yml")
        ParsePcieExtendedCap(extCapsDB)    
        DumpResultYaml(extCapsDB, "ExtCaps")
        PrintCaps(extCapsDB)
    return


def BitMarks(bitNum):
    print("  ", end="")  # align with the leading bar "|"
    for i in range(bitNum):
        print(f"{bitNum - 1 - i: <4}", end="")
    print()
    return


def Cap(capId, capName, capOffset):
    print(f"[{hex(capId)[2:].upper():0>4}h] {capName} @ {capOffset}")

def Reg(regName, regOffset, regValue):
    print(f"[{hex(regOffset)[2:].upper():0>3}h] {regName} = 0x{hex(regValue)[2:].upper()}")

def Field(fieldName, lowBitNum, hiBitNum, fieldVal):
    fieldValWidth = (hiBitNum - lowBitNum + 1 + 3) // 4  # integer division
    print (f"[{hiBitNum:0>2}:{lowBitNum:0>2}] - {fieldName}: 0x{hex(fieldVal)[2:].upper():0>{fieldValWidth}}")

def Line(length):
    print("-"*length)


def Bit(value):
    if (value != 1 and value != 0):
        print("Wrong bit value!")
        sys.exit(1)
    print(f" {value} |", end="")


def PrintCapPretty(capId, capObj):
    '''
    Display the capability similar to the diagrams in PCIe spec.

    15  14  13  12  11  10  9   8   7   6   5   4   3   2   1   0
    -----------------------------------------------------------------
    | 1 | 0 | 1 | 0 | 0 | 1 | 1 | 0 | 1 | 0 | 1 | 0 | 0 | 1 | 1 | 0 |
    -----------------------------------------------------------------
    '''
    regCapOffsets = capObj.keys()
    displayWidthBit = 4
    capName = capObj["Name"]
    capOffset = capObj["Offset"]
    Cap(capId, capName, capOffset)
    Line(len(capName) + len(hex(capId)) + len(capOffset) + 2 + 4 + 1 + 2)
    for regCapOffset in regCapOffsets:
        if (type(regCapOffset) is not int):
            continue
        regObj = capObj[regCapOffset]
        regName = regObj["Name"]
        regValue = int(regObj["Value"], 16)
        regBitNum = regObj["Width"] * 8
        displayWidthReg = regBitNum * displayWidthBit
        Reg(regName, regCapOffset, regValue)
        BitMarks(regBitNum)
        Line(displayWidthReg + 1)  # 1 for the leadning bar "|"
        print("|", end="")  # leading bar "|"
        for i in range(regBitNum):
            Bit((regValue >> (regBitNum - i - 1)) & 1)
        print()
        Line(displayWidthReg + 1)
    print()
    return

def PrintRegFields(capId, capObj):
    regCapOffsets = capObj.keys()
    capName = capObj["Name"]
    capOffset = capObj["Offset"]
    Cap(capId, capName, capOffset)
    for regCapOffset in regCapOffsets:
        if (type(regCapOffset) is not int):
            continue
        regObj = capObj[regCapOffset]
        regName = regObj["Name"]
        regVal = int(regObj["Value"], 16)
        print("  ", end="")
        Reg(regName, regCapOffset, regVal)
        if (not args.field):
            continue
        for fieldKey in regObj.keys():
            if (type(fieldKey) is int):
                fieldObj = regObj[fieldKey]
                fieldName = fieldObj["Name"] 
                lowBitNum = fieldKey
                hiBitNum = fieldObj["HiBit"]
                fieldVal = GetBitField(regVal, lowBitNum, hiBitNum)
                print("    ", end="")
                Field (fieldName, lowBitNum, hiBitNum, fieldVal)


def PrintCaps(capsDB):
    for capId in capsDB.keys():
        capObj = capsDB[capId]
        capName = capObj["Name"]
        if ("Offset" in capObj.keys()): # cap exists
            if (args.pretty):
                PrintCapPretty(capId, capObj)
            PrintRegFields(capId, capObj)
        else:
            print (f"Cap Not found: {capName}")
        print()
    print()
    return

def ParseHeader01(headerObj):
    for regOffset in headerObj.keys():
        if(type(regOffset) is not int):
            continue
        regObj = headerObj[regOffset]
        regVal = ConfigRead(regOffset, regObj["Width"])
        regObj["Value"] = regVal
    return

def ParseHeader(headersDB):
    headerType = GetHeaderType()
    if(headerType == 0):
        print("Type 0 Header:")
        ParseHeader01(headersDB[0])
    if(headerType == 1):
        print("Type 1 Header:")
        ParseHeader01(headersDB[1])
    print("--------------")
    return

def PrintHeader(headerObj):
    for regOffset in headerObj.keys():
        if (type(regOffset) is not int):
            continue
        print(f"{str.rjust(hex(headerObj[regOffset]["Value"])[2:], 8)}h @ {hex(regOffset)} {headerObj[regOffset]["Name"]}")
    return

def PrintHeader01(headersDB):
    headerType = GetHeaderType()
    if(headerType == 0):
        PrintHeader(headersDB[0])
    if(headerType == 1):
        PrintHeader(headersDB[1])
    print()
    return


def ParseArgs():
    global parser
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--cap", action="store_true", help="Parse capability")
    parser.add_argument("-ec", "--extcap", action="store_true", help="Parse extended capability")
    parser.add_argument("-f", "--field", action="store_true", help="Parse detailed fields")
    parser.add_argument("-p", "--pretty", action="store_true", help="Pretty print the register")
    parser.add_argument("-d", "--dump", help="Dump file")
    parser.add_argument("--header", action="store_true", help="Parse header")
    parser.add_argument("-r", "--raw", action="store_true", help="Output raw 4K config")

    global args
    args = parser.parse_args()

if __name__ == "__main__":
    ParseArgs()
    if(args.dump is None):
        parser.print_help()
        sys.exit(1)
    Get4KDump()
    ParseConfig()
    sys.exit(0)
