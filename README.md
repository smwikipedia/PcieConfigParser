# PcieConfigParser
**Please use Python 3.x.**

A script to parse the 4KB configration space dump of a PCIe device.

```
usage: PcieParser.py [-h] [-c] [-ec] [-f] [-p] [-d DUMP] [--header]

options:
  -h, --help            show this help message and exit
  -c, --cap             Parse capability
  -ec, --extcap         Parse extended capability
  -f, --field           Parse detailed fields
  -p, --pretty          Pretty print the register
  -d DUMP, --dump DUMP  Dump file
  --header              Parse header
```

User needs to first obtain a dump of the 4KB configuration space.
And then specify the registers of interest in the yaml schema file.
This yaml schema file is used to parse the PCIe config space.

### The dump file

```
2023-10-12 09:10:54	  00000040: 00 00 00 00 00 00 00 00-00 00 00 00 00 00 00 00  *................*
```
The offset and values are mandatory.
Each line must contain 16 bytes of config space content
The total dump must contain 0xFFF bytes
Otherparts like the timestamp are insignificant.


### The yaml schema file
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

The provided `Caps.yml` and `ExtCaps.yml` are not exhaustive.
So only some header registers, capabilities and extended capabilities can be parsed.
Users can add registers of interest to the yaml files.
The fidelity of result depends on the fidelity of the yaml schema file.

**And if you can contribute more schemas, I will be more than grateful!**

A PCI_Code-ID_r_1_11__v24_Jan_2019.pdf spec is added for reference.
For detailed capability registers please check the PCIe spec.

The script will parse the config space and generates a result yaml file with:

- offset of detected capablities
- values of each register of interest
- values of detailed register fields

And also print the register values in a pretty format. Such as:

```
[000Eh: ARI Extended Capability @ 0x140]
----------------------------------------
[000h] PCI Express Capability List Register (00h) @ 0x0 = 0x1501000E
  31  30  29  28  27  26  25  24  23  22  21  20  19  18  17  16  15  14  13  12  11  10  9   8   7   6   5   4   3   2   1   0
---------------------------------------------------------------------------------------------------------------------------------
| 0 | 0 | 0 | 1 | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 0 |
---------------------------------------------------------------------------------------------------------------------------------
[004h] ARI Capability Register @ 0x4 = 0x0
  15  14  13  12  11  10  9   8   7   6   5   4   3   2   1   0
-----------------------------------------------------------------
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
-----------------------------------------------------------------
[006h] ARI Control Register @ 0x6 = 0x0
  15  14  13  12  11  10  9   8   7   6   5   4   3   2   1   0
-----------------------------------------------------------------
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
-----------------------------------------------------------------

[000Eh: ARI Extended Capability @ 0x140]
  [000h] PCI Express Capability List Register (00h) @ 0x0 = 0x1501000E
    [15:00] - Capability ID: 0x000E
    [19:16] - Capability Version: 0x1
    [31:20] - Next Capability Offset: 0x150
  [004h] ARI Capability Register @ 0x4 = 0x0
    [00:00] - MFVC Function Groups Capability (M): 0x0
    [01:01] - ACS Function Groups Capability (A): 0x0
    [07:02] - RsvdP: 0x00
    [15:08] - Next Function Number: 0x00
  [006h] ARI Control Register @ 0x6 = 0x0
    [00:00] - MFVC Function Groups Enable (M): 0x0
    [01:01] - ACS Function Groups Enable (A): 0x0
    [03:02] - RsvdP: 0x0
    [06:04] - Function Group: 0x0
    [15:07] - RsvdP: 0x000
```
