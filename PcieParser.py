'''
A script to parse the 4KB configration space dump of a PCIe device.
User need to first obtain a dump of the 4KB configuration space.
And then create a yaml file to specify the capabilities of interest.
The script will use the yaml to search and parse the PCIe config space.
Currently, only capabilities and extended capabilities can be parsed.

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
                print(f"{hex(offset).upper()[2:]:0>8}: {dumpLine}")
                dumpLine = dumpLine.replace("-", " ")
                dumpBytes = re.findall(reByte, dumpLine)
                Config4K.extend([int(x, 16) for x in dumpBytes])
                expectedOffset += 16
            if (offset == 0xFF0):
                collect = False
        line = f.readline()

# Little endian


def ConfigRead(offset, regWidth):  # regWidth in byte
    if (not regWidth in [1, 2, 3, 4]):
        print("Bad register width!")
        sys.exit(1)
    Value = 0
    for i in range(regWidth):
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
        if (type(regCapOffset) is not int):
            continue
        regObj = capObj[regCapOffset]
        regWidthNum = capObj[regCapOffset]["Width"]
        valWidth = 2 * regWidthNum  # a byte has two hex digit
        regOffset = capOffset + regCapOffset
        regVal = ConfigRead(regOffset, regWidthNum)
        # regObj["Value"] = f"{bin(regVal)[2:]:0>{valWidth*4}}"
        regObj["Value"] = f"0x{hex(regVal)[2:].upper():0>{valWidth}}"
        # If register fields are specified, just continue to parse it.
        for fieldKey in regObj.keys():
            if (type(fieldKey) is int):
                fieldObj = regObj[fieldKey]
                lowBitNum = fieldKey
                hiBitNum = fieldObj["HiBit"]
                fieldVal = GetBitField(regVal, lowBitNum, hiBitNum)
                fieldValWidth = (hiBitNum - lowBitNum + 1 +
                                 3) // 4  # integer division
                fieldObj["Value"] = f"0x{hex(fieldVal)[2:].upper():0>{fieldValWidth}}"


def ParsePciCap(capsDB):
    '''
    Begin from offset 0x34, a 1-byte link
    [7:0] Extended Cap ID
    [15:8] Next Cap Pointer
    '''
    print("PCI Capabilities:")
    capOffset = ConfigRead(0x34, 1)
    while (capOffset):
        capId = ConfigRead(capOffset, 1)
        print(f"{hex(capId).upper()[2:]:0>2}h @ {hex(capOffset).upper()[2:]:0>2}h")
        ParseSinglePciPcieCap(capsDB, capId, capOffset)
        capOffset = ConfigRead(capOffset + 1, 1)
    return


def ParsePcieExtendedCap(extCapsDB):
    '''
    Begin from offset 0x100
    [15:0] Extended Cap ID
    [19:16] Cap Ver.
    [31: 20] Next Cap Offset
    '''
    print("PCIe Capabilities:")
    capOffset = 0x100
    while True:
        data = ConfigRead(capOffset, 4)
        capId = GetBitField(data, 0, 15)
        capVer = GetBitField(data, 16, 19)
        print(
            f"{hex(capId).upper()[2:]:0>4}h of v{hex(capVer).upper()[2:]} @ {hex(capOffset).upper()[2:]:0>3}h")
        ParseSinglePciPcieCap(extCapsDB, capId, capOffset)
        capOffset = GetBitField(data, 20, 31)
        if (capOffset == 0):
            break
    return


def LoadRegTemplate(capTemplateFile):
    with open(capTemplateFile, "r") as f:
        try:
            capsDB = yaml.safe_load(f)
        except yaml.YAMLError as ex:
            print(ex)
            sys.exit(1)
    return capsDB


def DumpCapsDbWithValue(capsDB, capTemplateFile):
    timestamp = time.strftime("_%Y%m%d-%H%M%S")
    dumpFileName = Path(capTemplateFile).stem
    dumpFileSuffix = capTemplateFile[capTemplateFile.rfind("."):]
    dumpFileName = "Result." + dumpFileName + timestamp + dumpFileSuffix
    with open(dumpFileName, 'w', encoding='utf8') as f:
        yaml.dump(capsDB, f)


def ParsePcie():
    if (args.cap):
        capsDB = LoadRegTemplate(args.cap)
        ParsePciCap(capsDB)
        DumpCapsDbWithValue(capsDB, args.cap)
        print()
        PrintCaps(capsDB)
    print()
    if (args.extcap):
        extCapsDB = LoadRegTemplate (args.extcap)
        ParsePcieExtendedCap(extCapsDB)    
        DumpCapsDbWithValue(extCapsDB, args.extcap)
        print()        
        PrintCaps(extCapsDB)
    return


def BitMarks(bitNum):
    print("  ", end="")  # align with the leading bar "|"
    for i in range(bitNum):
        print(f"{bitNum - 1 - i: <4}", end="")
    print()
    return


def Cap(capId, capName, capOffset):
    print(f"[0x{hex(capId)[2:].upper():0>3}: {capName} @ {capOffset}]")

def Reg(regName, regOffset, regValue):
    print(f"[{hex(regOffset)[2:].upper():0>3}h] {regName} @ 0x{hex(regOffset)[2:].upper()} = 0x{hex(regValue)[2:].upper()}")

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
        if ("Offset" in capObj.keys()):
            PrintCapPretty(capId, capObj)
            PrintRegFields(capId, capObj)
        else:
            print (f"Cap Not found: {capName}")
    return


def ParseArgs():
    global parser
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--cap", help="Capability schema YAML")
    parser.add_argument("-ec", "--extcap", help="Extended capability schema YAML")
    parser.add_argument("-d", "--dump", help="Dump file")
    global args
    args = parser.parse_args()

if __name__ == "__main__":
    ParseArgs()
    if(args.dump is None):
        parser.print_help()
        sys.exit(1)
    Get4KDump()
    ParsePcie()
    sys.exit(0)
