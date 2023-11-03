# PcieConfigParser
**Please use Python 3.x.**

A script to parse the 4KB configration space dump of a PCIe device.

User needs to first obtain a dump of the 4KB configuration space.
And then create a yaml schema file to specify the capabilities of interest.
The script will use the yaml to search and parse the PCIe config space.
Currently, only capabilities and extended capabilities can be parsed.


The dump file should be of below format:

```
2023-10-12 09:10:54	  00000040: 00 00 00 00 00 00 00 00-00 00 00 00 00 00 00 00  *................*
```
The offset and values are mandatory.
Each line must contain 16 bytes.
The total dump must contain 0xFFF bytes
The timestamp is insignificant.

Because PCI Capability and PCIe Extended Capability can have same IDs, so we use two
seperate yaml shema files to describe them, respectively.

The yaml schema file is defined as below:

```
0x01: # cap ID
  Name: PCI Power Management Capability
  0x0: # reg offset
    Name: Power Management Capabilities Register (00h)
    Width:  4 # reg width in byte
    0: # Bit field start bit
      Name: Capability ID
      HiBit: 7 # Bit field end bit
    8:
      Name: Next Capability Pointer
      HiBit: 15
    16:
      Name: Version
      HiBit:  18

```
The bit filed entries are not mandatory.

The provided CapSlim.yml and CapRich.yml are not exhaustive.

CapSlim doesn't specify the detailed register bit field. While CapRich specifies a few.

If additional capabilities are desried, user can specify them according to
the schema below.

(**And if users can contribute back their capability schemas, I will be more than grateful!**)

A PCI_Code-ID_r_1_11__v24_Jan_2019.pdf spec is added for reference.
For detailed capability registers please check the PCIe spec.

The script will parse the config space and generates a result yaml file with:

- offset of detected capablities
- values of each register within capabilities

And also print the register values in a pretty format. Such as:

```
[0x10: SR-IOV Extended Capability @ 0x200]
------------------------------------------
PCI Express Extended Capablility Header @ 0x0 = 0x27410010
  31  30  29  28  27  26  25  24  23  22  21  20  19  18  17  16  15  14  13  12  11  10  9   8   7   6   5   4   3   2   1   0
---------------------------------------------------------------------------------------------------------------------------------
| 0 | 0 | 1 | 0 | 0 | 1 | 1 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
---------------------------------------------------------------------------------------------------------------------------------
```