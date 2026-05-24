#!/bin/bash
#
# Full Texas RRC lease discovery script.
#
# Searches all 13 districts with all common name patterns.
# Expected runtime: 10-15 hours.
# Output: ./leases_discovered.csv
#
# Usage:
#   ./discover_all_leases.sh              # normal run (resumes from last checkpoint)
#   ./discover_all_leases.sh --clear      # clear history and redo everything
#
# If interrupted (Ctrl+C), re-run the same command. Only remaining
# (district, pattern) combos will be searched.

set -euo pipefail

CLEAR_HISTORY=""
if [[ "${1:-}" == "--clear" || "${1:-}" == "--clear-history" ]]; then
    CLEAR_HISTORY="--clear-history"
    echo ">>> Clearing discovery history and redoing all searches"
fi

STATE_FILE="./data/discovery_state.json"

DISTRICTS="01,02,03,04,05,06,6E,7B,7C,08,8A,09,10"

PATTERNS="AAA,ABB,ABC,ACE,ADA,ADO,AGE,ALE,ALL,AMA,\
ANA,AND,ANN,APE,ARC,ARK,ARM,ASH,ATE,AUB,\
BAD,BAR,BAY,BEE,BEL,BEN,BIG,BIR,BLE,BLU,\
BOG,BOW,BOX,BOY,BRA,BRO,BRU,BRY,BUCK,BUF,\
BUR,BUS,BYR,CAD,CAL,CAM,CAN,CAR,CAT,CED,\
CHA,CHE,CHO,CIT,CLAY,CLE,CLI,CLO,COA,COD,\
COL,COM,CON,COO,COR,COS,COV,COW,CRA,CRE,\
CRO,CRY,CUB,CUT,DAL,DAN,DAV,DAY,DEE,DEL,\
DEN,DEW,DIA,DIN,DOG,DON,DOT,DOV,DOW,DRY,\
DUB,DUN,DUR,EAG,EAR,EAS,EDG,EDW,ELL,ELM,\
ENG,ERS,ESC,ESS,EST,ETH,EUN,EVA,EVE,EWI,\
FAL,FAN,FAR,FAY,FED,FEE,FEL,FEN,FER,FIN,\
FIS,FIT,FLA,FLO,FLU,FOG,FOR,FRE,FUL,\
GAL,GAM,GAR,GAS,GAY,GEO,GER,GIB,GIL,GIN,\
GLO,GOD,GOO,GOR,GOT,GRA,GRE,GRI,GRO,GUL,\
HAG,HAM,HAN,HAR,HAS,HAT,HAY,HEL,HEN,HIC,\
HIL,HOD,HOG,HOL,HOP,HOU,HOW,HUB,HUD,HUN,\
IAN,ICE,IDA,ILL,IND,ING,INK,ION,IRE,IRV,\
JAC,JAM,JAY,JEN,JES,JEW,JIM,JOH,JON,JOR,\
JUD,KAY,KEE,KEN,KID,KIN,KIT,LAB,LAC,LAF,\
LAG,LAN,LAR,LAS,LAT,LEE,LEG,LEN,LEO,LES,\
LEV,LEW,LEY,LIL,LIN,LIT,LIV,LOG,LON,LOU,\
LOW,LUC,LUF,LYN,MAC,MAD,MAN,MAR,MAS,MAT,\
MAY,MCD,MCK,MEL,MER,MIA,MIC,MID,MIL,MIN,\
MIS,MIT,MOB,MOC,MOD,MOO,MOR,MOS,MOT,MUD,\
NAN,NAT,NEE,NEW,NIB,NIC,NOL,NOR,OAK,OIL,\
OLD,ONE,ORE,ORI,OSW,OTT,OWE,OXF,PAL,PAR,\
PAT,PAU,PAY,PEA,PEE,PEN,PER,PET,PHE,PIE,\
PIN,PIT,PLY,POC,POE,POL,PON,POP,POR,POS,\
PRE,PRI,PRO,PUL,PUR,QUE,QUI,RAD,RAL,RAM,\
RAN,RAP,RAY,REA,RED,REE,RES,RHO,RIC,RID,\
RIG,RIL,RIS,RIV,ROA,ROB,ROC,ROD,ROG,ROL,\
ROM,ROO,ROS,ROW,ROY,RUB,RUD,RUG,RUP,RUS,\
SAC,SAD,SAL,SAN,SAP,SAT,SAU,SAV,SAY,SEA,\
SEN,SER,SHA,SHE,SHI,SHO,SIC,SIM,SIN,SIS,\
SKI,SMI,SMY,SOM,SON,SOR,SOU,SPA,SPI,SPR,\
STA,STE,STO,STR,STU,SUL,SUN,SUP,SUR,SWI,\
SYL,SYR,TAM,TAN,TAY,TED,TEN,TER,TEX,THE,\
THO,TIL,TIM,TIT,TOB,TOD,TOM,TON,TOP,TOR,\
TOW,TRI,TRO,TUB,TUC,TUN,TUR,UNI,UNIT,UPP,\
VAN,VAS,VER,VIA,VIC,VIL,VIN,VIS,VOL,WAD,\
WAL,WAN,WAR,WAT,WAX,WAY,WEB,WEL,WEN,WES,\
WHI,WIC,WIL,WIN,WIS,WOA,WOL,WOO,WOR,WRI,\
YAK,YAL,YAR,YEA,YOR,YOU,ZAC,ZAR,ZEE"

START_TIME=$(date +%s)
LOGFILE="lease_discovery_$(date +%Y%m%d_%H%M%S).log"

echo "=== Texas RRC Lease Discovery ==="
echo "Districts:  $(echo "$DISTRICTS" | tr ',' ' ')"
echo "Patterns:   $(echo "$PATTERNS" | tr ',' '\n' | wc -l)"
echo "Output:     ./leases_discovered.csv"
echo "Log:        $LOGFILE"
echo "Started:    $(date)"
echo ""

# Run discovery per-district so partial results survive interruption
for DIST in $(echo "$DISTRICTS" | tr ',' ' '); do
    DIST_OUT="./leases_district_${DIST}.csv"

    # Check if this district's patterns are already all done in state file
    DIST_PENDING=""
    if [ -f "$STATE_FILE" ] && [ "$CLEAR_HISTORY" = "" ]; then
        DIST_PENDING=$(python3 -c "
import json, sys
with open('$STATE_FILE') as f:
    state = json.load(f)
done = set(state.get('$DIST', []))
all_patterns = '''$PATTERNS'''.replace('\\\\', '').replace('\n', '').split(',')
pending = [p for p in all_patterns if p not in done]
print(len(pending))
" 2>/dev/null || echo "unknown")
    else
        DIST_PENDING="all"
    fi

    if [ "$DIST_PENDING" = "0" ] && [ -f "$DIST_OUT" ]; then
        COUNT=$(tail -n +2 "$DIST_OUT" | wc -l)
        echo "[$(date)] District $DIST already complete: $COUNT leases (skipping)" | tee -a "$LOGFILE"
        echo ""
        continue
    fi

    echo "[$(date)] Starting district $DIST → $DIST_OUT" | tee -a "$LOGFILE"

    python3 lease_discovery.py \
        --districts "$DIST" \
        --patterns "$PATTERNS" \
        --output "$DIST_OUT" \
        --state-file "$STATE_FILE" \
        $CLEAR_HISTORY \
        2>&1 | tee -a "$LOGFILE"

    COUNT=$(tail -n +2 "$DIST_OUT" | wc -l)
    echo "[$(date)] District $DIST complete: $COUNT leases" | tee -a "$LOGFILE"
    echo ""
done

# Merge all district files
echo "[$(date)] Merging all district files..." | tee -a "$LOGFILE"

python3 -c "
import csv, glob

all_leases = {}
for f in sorted(glob.glob('./leases_district_*.csv')):
    with open(f) as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            key = (row['lease_number'], row['district'])
            if key not in all_leases:
                all_leases[key] = row

with open('./leases_discovered.csv', 'w', newline='') as out:
    writer = csv.DictWriter(out, fieldnames=['lease_number', 'district', 'name', 'well_type'])
    writer.writeheader()
    for lease in sorted(all_leases.values(), key=lambda x: (x['district'], x['lease_number'])):
        writer.writerow(lease)

print(f'Merged {len(all_leases)} unique leases into ./leases_discovered.csv')
" 2>&1 | tee -a "$LOGFILE"

END_TIME=$(date +%s)
ELAPSED=$(( (END_TIME - START_TIME) / 60 ))

echo ""
echo "=== Discovery Complete ==="
echo "Total runtime: ${ELAPSED} minutes"
echo "Output: ./leases_discovered.csv"
echo "Log: $LOGFILE"
echo "Finished: $(date)"
