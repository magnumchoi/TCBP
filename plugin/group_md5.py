#!/usr/bin/env python3
"""
[ko][플러그인 개요]
이름: group_md5.py
버전: v1.6
타입: TCBP BatchSession 플러그인
목적: 파일들을 이름 유사도로 그룹핑해 그룹별 MD5 목록(.md5) 파일 생성
설명: TCBP를 통해 run(session)으로 호출되거나, tcbp 없이 단독 CLI로 실행할 수 있다.
독립실행시:
    python group_md5.py <list_file> [bom=true] [chunk_size=64]
기타:
- 같은 폴더 내 파일명에서 알려진 노이즈(가변 구간 PART/DISC 등, 보호되지 않은 순번)만
  정규식으로 제거해 정규화된 제목을 만들고, 그 제목이 완전히
  같은 파일끼리 그룹화해 그룹별로 .md5 파일 하나를 생성한다(_normalize_title 참고).
  품번(화이트리스트 등록 레이블+숫자, 또는 제목/태그와 함께 나오는 letters+숫자)은
  노이즈가 아니라 보호 식별자라 항상 제목에 그대로 남으므로, 다른 품번을 가진 파일은
  제목 자체가 달라져 자연히 분리된다.
- 진행률은 session.log()를 거치지 않고 stdout에 \r로 숫자 %만 직접 출력한다.
  (BatchSession은 병렬 처리가 없어 안전. rich 등 ANSI 커서 이동 라이브러리는 사용하지 않음)
- 그룹 처리가 끝난 뒤의 최종 결과("생성됨: xxx.md5 (N개 파일)")만 log()로 남긴다.
버전이력:
- v1.0 : 최초 작성
- v1.1 : 파일명을 토큰 단위로 분해한 뒤, 토큰별 가중치를 매겨 유사도 점수를 계산하고
  임계값을 넘으면 같은 그룹으로 판별하는 방식(가중치 기반 유사도 판별 로직).
- v1.2 : 가중치 유사도 판별을 폐기하고, 정규식으로 노이즈(가변 구간/미보호 순번)만
  제거한 정규화 제목의 완전일치로 그룹을 판별하는 방식으로 재설계. 하이픈 없는
  품번(KNOWN_LABEL_PREFIXES 화이트리스트)을 보호 식별자로 인정하는 규칙 추가.
  (AAA001, AAA002는 같은 AAA그룹으로 인식하지만 IPZZ100, IPZZ101은
  IPZZ가 화이트 리스트에 들어있어서 다른 그룹으로 인식함.)
- v1.3 : 화이트리스트에 없는 레이블이라도, 매치(letters+digits)를 제거했을 때 파일명에
  다른 텍스트(제목/태그)가 남아 있으면 보호 식별자로 인정하는 "컨텍스트" 규칙 추가
  (_has_context). 하이픈 유무는 더 이상 보호 여부를 결정하지 않는다 — 파일명이
  사실상 코드 하나뿐일 때만(컨텍스트 없음) 순번으로 취급한다. 화이트리스트가
  등록돼 있으면 컨텍스트와 무관하게 항상 우선 적용된다. (예: "[MOODYZ] MIHD009"는
  MIHD가 화이트리스트에 없어도 [MOODYZ] 태그가 컨텍스트가 되어 보호됨. 반대로
  화이트리스트에 없는 레이블이 "AAA-001"처럼 파일명 전체를 이루는 코드뿐이면,
  하이픈이 있어도 순번으로 취급되어 숫자가 제거된다.)
- v1.4 : 품번 바로 뒤, 파일명 맨 끝에 붙은 언더바(들)를 노이즈로 보고 제거하는 규칙
  추가(PART_NUM_TRAILING_UNDERSCORE_RE). 보호 여부 판단 전에 적용되어 판단 자체에는
  영향을 주지 않는다. (예: "...MIHD009"와 "...MIHD009_"는 같은 품번으로 취급되어 한
  그룹으로 묶인다.)
- v1.5 : \r 진행률 카운터에 전체 파일 카운터([i/n])뿐 아니라 현재 그룹 내에서 몇
  번째 파일을 처리 중인지 보여주는 그룹 내 순번 카운터([gp/gt])도 함께 표시하도록
  변경.
- v1.6 : 품번 바로 뒤, 파일명 맨 끝에 붙는 노이즈 인정 범위를 언더바 전용에서
  "영문자 1개(a-z/A-Z, 예: v/r/c) + 언더바(들)" 조합까지 확대(PART_NUM_TRAILING_SUFFIX_RE,
  구 PART_NUM_TRAILING_UNDERSCORE_RE 대체). 예: "...START612v", "...START612v_",
  "...START612v__"가 모두 "...START612"와 같은 품번으로 취급되어 한 그룹으로 묶인다.
  보호 여부 판단 전에 적용되어 판단 자체에는 영향을 주지 않는 점은 v1.4와 동일.

[en][Plugin Overview]
Name: group_md5.py
Version: v1.6
Type: TCBP BatchSession plugin
Purpose: Group files by filename similarity and generate a grouped MD5 (.md5) list file per group
Description: Can be called via run(session) through TCBP, or run standalone (without tcbp).
Standalone execution:
    python group_md5.py <list_file> [bom=true] [chunk_size=64]
Notes:
- Builds a normalized title per filename within the same folder by stripping only known
  noise via regex (variable segments like PART/DISC, unprotected sequence numbers), then
  groups files whose normalized title is exactly equal, writing one
  .md5 file per group (see _normalize_title). A part number (a whitelisted label + digits,
  or letters + digits appearing alongside a title/tag) isn't noise — it's a protected
  identifier that always stays in the title, so files with different part numbers
  naturally end up with different titles and stay apart.
- Progress is printed directly to stdout as a numeric % using \r, bypassing session.log()
  (safe because BatchSession never runs in parallel; ANSI-cursor-based libraries such as rich are
  intentionally not used).
- Only the final result per group (e.g. "created: xxx.md5 (N files)") is reported via log().
Version history:
- v1.0 : Initial version.
- v1.1 : Tokenized filenames, weighted each token, and computed a similarity score;
  files above a threshold were judged to be in the same group (weighted-similarity
  matching logic).
- v1.2 : Dropped weighted-similarity matching; redesigned around stripping only known
  noise (variable segments / unprotected sequence numbers) via regex and grouping by
  exact match of the resulting normalized title. Added a rule recognizing hyphen-less
  part numbers (KNOWN_LABEL_PREFIXES whitelist) as protected identifiers.
  (AAA001 and AAA002 are recognized as the same AAA group, but IPZZ100 and IPZZ101 are
  recognized as separate groups because IPZZ is registered in the whitelist.)
- v1.3 : Added a "context" rule (_has_context): even for a label that isn't whitelisted, a
  match (letters+digits) is now treated as protected if removing it leaves other text (a
  title/tag) behind in the filename. A hyphen no longer decides protection on its own — a
  match is treated as a sequence number only when the filename is effectively nothing but
  the code (no context). The whitelist still takes priority whenever the label is
  registered. (E.g. "[MOODYZ] MIHD009" is now protected because the [MOODYZ] tag counts as
  context, even though MIHD isn't whitelisted. Conversely, an unwhitelisted label that
  makes up the entire filename, like "AAA-001", is treated as a sequence number and has its
  digits stripped even though it has a hyphen.)
- v1.4 : Added a rule stripping underscore(s) glued directly after a part number at the
  very end of the filename as noise (PART_NUM_TRAILING_UNDERSCORE_RE). Applied before the
  protection decision, so it never affects that decision. (E.g. "...MIHD009" and
  "...MIHD009_" are now treated as the same part number and grouped together.)
- v1.5 : The \r progress counter now shows both the overall file counter ([i/n]) and a
  within-group position counter ([gp/gt]) indicating which file of the current group is
  being processed.
- v1.6 : Widened the noise glued right after a part number at the very end of the
  filename from underscores-only to "a single letter (a-z/A-Z, e.g. v/r/c) + underscore(s)"
  (PART_NUM_TRAILING_SUFFIX_RE, replacing PART_NUM_TRAILING_UNDERSCORE_RE). E.g.
  "...START612v", "...START612v_", and "...START612v__" are now all treated as the same
  part number as "...START612" and grouped together. Still applied before the protection
  decision, so it never affects that decision, same as v1.4.
"""
import sys
import os
import re
import hashlib
import time
from pathlib import Path
from collections import defaultdict
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # [ko] tcbp.py가 있는 상위 폴더 / [en] parent folder containing tcbp.py
from tcbp import plugin, BatchSession, BatchResult, parse_params, _to_bool, _truncate_filename

TRUNCATE_LENGTH = 60
PROGRESS_UPDATE_INTERVAL = 1.5  # [ko] 진행률 콜백 최소 호출 간격(초) — 오리지널 refresh_per_second=0.67과 동일 / [en] minimum interval (seconds) between progress callbacks — matches the original refresh_per_second=0.67

# [ko] 가변 식별자(part/disc/cd/vol/ep/track + 번호)의 접두어 데이터.
#      정규식은 코드에서 동적으로 생성되므로, 새 접두어는 이 목록에만 추가하면 된다.
# [en] Prefix data for variable identifiers (part/disc/cd/vol/ep/track + number).
#      The regex is generated dynamically from this list, so adding a new prefix
#      only requires editing this set.
VARIABLE_PREFIXES = {"DISC", "PART", "CD", "VOL", "EP", "TRACK"}

# [ko] <레이블><번호> 품번(예: "SONE100", "MIHD-009")을 위한 화이트리스트.
#      대부분의 실제 품번은 제목/태그와 함께 나타나 컨텍스트 규칙(_has_context)만으로도
#      보호되지만, 파일명이 코드 하나뿐인 경우(컨텍스트 없음)엔 "AAA001"(순번, 병합돼야
#      함)과 "SONE100"(품번, 병합되면 안 됨)을 문자열 구조만으로 구별할 수 없다 — 그래서
#      여기 등록된 레이블에 한해, 컨텍스트가 없어도 항상 보호 식별자로 인정한다. 새
#      레이블은 이 목록에만 추가하면 된다.
#      알려진 한계: "3DSVR"/"T28"/"T38"처럼 접두어 자체에 숫자가 섞인 항목은 문자/숫자
#      경계 분리 때문에 하이픈 없이 붙어 있으면 인식되지 않는다(하이픈이 있으면 정상 인식).
# [en] Whitelist for <label><number> part numbers (e.g. "SONE100", "MIHD-009"). Most real
#      part numbers appear alongside a title/tag, so the context rule (_has_context) alone
#      already protects them; but when a filename is nothing but the bare code (no
#      context), "AAA001" (a sequence number, should merge) and "SONE100" (a real part
#      number, must never merge) are structurally indistinguishable — so labels registered
#      here are always protected even without context. Add a new label by editing this
#      list only.
#      Known limitation: entries with a digit embedded in the prefix itself (e.g. "3DSVR",
#      "T28", "T38") won't be recognized when hyphen-less, since the letter/digit boundary
#      split breaks them apart first (a hyphenated form still works fine).
KNOWN_LABEL_PREFIXES = frozenset("""
AEGE,WAWA,OAE,AKDL,FSET,MANE,TAMO,AND,AP,AQSH,AARM,ARMQ,ASEX,ADN,ATAD,ATID,ATVR,JBD,RBD,RBK,
SAME,SHKD,SSPD,YUJ,APAA,APAK,APGH,APKH,APNS,AVOP,AVSA,GMEM,GMEN,KIMU,NAKA,SVS,TAAK,USBA,AVVR,
ARAN,BEFG,DAKH,DARG,DBAM,DBBA,DBER,DBVB,DCLB,DDDA,DDGB,DDGM,DDHG,DDHS,DDNA,DDNG,DDSA,DFMS,DGSI,
DHHS,DJDH,DJJJ,DJUD,DKIK,DKNG,DLEP,DMKG,DMKS,DNIA,DONN,DPCD,DPEP,DPGR,DPHD,DPIK,DPNK,DPSJ,DRAN,
DRNS,DSEN,DSJA,DUIB,DUPT,DVCR,DVKA,DXBB,DXDB,DXEB,DXHK,DXMG,DXMJ,DXNH,DXPD,DYIB,DZSS,MDOG,VRRB,
BAGR,BAHP,TMCY,BAZX,BZVR,MDB,MDBK,SMV,BF,PTS,ZEX,MBRAB,MBRAZ,MBRBN,CND,CACA,CAFR,CAMI,CAPI,CWP,
CWPBD,EUUD,JRZE,NUKA,XMOM,BTH,SVGAL,SVHOT,CMA,CMC,CMF,CMN,CMV,CNY,DD,CSDX,COSVR,CRVR,DLDSS,DANDY,
DFDM,DFE,DPSVR,DVDES,DVDMS,DVEH,DVMM,DAC,DAL,DCXD,DEVR,DOCD,DOCP,FCH,FCP,HMRK,MFCO,MFCT,MGTD,SUKE,
DDB,DDFF,DDK,DDKM,DDOB,DDT,DWD,OMHD,RYDD,AAD,BLD,CAD,COD,DTSL,DTVR,ISD,NED,NLD,NHD,PED,EBOD,EBVR,
EBWH,EYAN,MKCK,ECR,SERO,ETQR,ETVCO,FAA,FWAY,FADSS,FCDSS,FLNO,FNS,FSDSS,FSVSS,FTHTD,MGOLD,JOHS,HOKS,
SS,AIDA,ALOG,CHUC,CIEL,DORI,FGEN,FJIC,FNEO,FNEW,FNTR,FONE,FSAN,FSBK,FSKI,FSYM,GAID,GAMA,GOLD,HAZE,
HOME,JOSI,KCOS,KDMN,KNAM,KNMB,KNSM,KSWP,LICN,LOCK,MSPK,NAPK,NAPS,NEBO,NECO,NEOS,NEXT,NMCH,NNNC,TANG,
TDMN,TENN,TGYM,TKOU,TSND,DEAB,FCVR,FINH,FPRE,JFB,JUFD,JUFE,JUNY,MANX,MEAD,NIMA,NYB,SVFLA,FOCS,AVZG,
KV,ABC,APO,CMI,CMO,FSB,FST,GES,HME,HWS,JTW,KPK,MCT,NCN,NIC,NMI,NNP,PAT,SPA,SRK,UMI,GNE,AYV,BJK,BUR,
COS,CUT,DOT,FIR,FTA,GAI,GLD,GON,GST,HDI,KAM,LOL,MIX,MMD,MRS,NFG,NST,ONI,PAN,RAN,RJK,SCR,SHJ,SIS,TUE,
VAL,YBA,ZXY,GVG,GVH,MVG,NVH,OVG,RVG,RVH,OTAT,GDTM,GOPJ,GRACE,MDVIJ,GUPP,BUKGA,BUKGB,BUKGC,CNSTV,
CSRAV,ERGZ,ERHAV,ERHBV,ERHV,EROFV,FANH,GGP,GGPVR,HMDNV,HMDSX,HMNX,INON,INSTV,KKWX,MAZO,MBRK,NIZX,
STVF,UINAV,XOX,AIDV,HMPD,HODV,HOMA,HOWY,HYSD,NEBB,NEOB,HHKL,HNTRZ,HUNBL,HUNT,HUNTA,HUNTB,HUNTC,IBW,
HPD,IDBD,IPBZ,IPIT,IPOK,IPSD,IPSE,IPTD,IPVR,IPX,IPZ,IPZZ,SUPD,BKSP,IDOL,IENE,IENF,IENFH,IEQP,IESM,
IESP,JFM,NBES,NDRA,NGOD,NKKD,NKTV,JUKF,JUMP,JUTN,CAWD,KANE,KAPD,KAVR,KAWD,KWBD,KWSD,BLK,KIBD,KIFD,
KIRD,KISD,SET,KTKQ,AVERV,BMVR,BIBIVR,BIKMVR,KDVR,KMVR,SAVR,TMVR,VRKM,KTDS,KTRA,UMD,ZIZG,LULU,BAK,
GKI,ISI,JYA,KRI,MAD,SPJK,STM,TKI,ZNN,ZRO,ACHJ,JUC,JUKD,JUL,JUMS,JUQ,JUR,JUSD,JUVR,JUX,JUY,MDON,MREC,
OBA,OBE,ROE,URE,MADV,MMBF,MMCPVR,MMKS,MMKZ,MMPV,MMSK,MMUS,MMYM,MMYU,MTABS,MTACO,MTALL,MTATA,MAXVR,
XV,XVSR,MXDLP,MXGS,MXSPS,MBDD,INOT,TDAN,HONB,KNWF,OTIN,MILK,EMKMP,MILD,MILV,MKMP,EDGD,LOVD,MDED,
MDHR,MDID,MDJD,MDLD,MDQD,MDRD,MDUD,MDVR,MDXD,MIAA,MIAB,MIAD,MIAE,MIAS,MIBD,MIDA,MIDD,MIDE,MIDV,MIFD,
MIGD,MIHD,MIID,MIKR,MIMK,MINT,MIQD,MIRD,MIVD,OVVR,MIXS,MIZD,MNGS,MOER,MFC,MFCC,MFCD,MFCS,MFDZ,MFOZ,MFTZ,
MIST,MTVR,MVSD,MEX,MTH,TEK,VRMT,ARSO,NATR,NAAC,AHD,AOT,ASPT,ISPT,JRJ,KUT,MOHA,NHDT,NHDTA,NHDTB,NHDTC,
NHVR,RCOD,RKSD,SBBD,SKRD,SMBD,TFJ,TOT,TSPT,YSPT,ZZZ,NEO,NOSKN,NSBB,AVGP,DHLD,DIC,DILD,DIV,DIVS,DKSB,
DKWT,DMOW,DOHI,DOKS,DORR,DOTM,DROP,DSJH,JKS,NBRD,TDBR,TDSU,OFSD,OLM,OMEG,ODFA,ODFB,ODFM,ODFP,ODFR,
ODFW,ONCE,ONEM,ONEX,ONEZ,PPBD,PPFD,PPMD,PPP,PPPD,PPPE,PPSD,PPVR,PKPD,PKPR,AMBI,AMBS,CLOT,HDKA,NACR,
NACT,NACX,ZMAR,PRBY,PRBYB,PBD,PGD,PID,PJD,PRED,PRST,PRTD,PRVR,PXD,ABF,ABP,ABS,ABW,AMA,BGN,CHN,DLV,
DOM,EDD,GNI,INU,JBS,JNT,KIT,KRV,MAS,MGT,PPT,PPX,PRD,PRDVR,PRVRSS,SAD,SNG,THU,VPC,WAT,WPC,WPS,YRH,
YRK,YRZ,YZF,PKTA,RCON,REAL,XRL,XRW,REBD,REBDB,REKU,RCT,RCTD,RCTS,RRCT,RBB,RKI,RVR,ROYD,TYSF,OFJE,
ONED,ONSD,SIVR,SNIS,SNOS,SOE,SONE,SSIS,SSNI,SVACE,SVBGR,SVCAO,SVDVD,SVERS,SVMGM,SVOMN,SVSHA,SVVRT,
ZOZO,SCOP,SCPX,WABB,SCBM,SCSS,SCUTE,SQDE,SQTE,SQTEVR,DLIS,HARU,HARUV,JBJB,MABP,MACB,SHM,SNKH,SNKP,
TPP,3DSVR,HYPN,KIRE,KMHRS,KUSE,MASD,MOGI,SDAB,SDAM,SDDE,SDDL,SDDM,SDEN,SDHS,SDJS,SDMF,SDMM,SDMS,
SDMT,SDMU,SDMUA,SDNM,SDNT,SDSI,SETM,SHYN,SODS,STAR,STARS,START,STKO,STZY,TIGR,MARAA,MBRAA,MBRAQ,
MBRBA,MBRBK,MBRBM,MBRBS,MMRAA,SPIVR,CAND,SKJK,SKSK,ICHK,SUN,SPRL,SW,SABA,SAMA,SUPA,TPPN,TPPS,TPVR,
CSCT,TCD,AUKB,AUKG,AUKS,AUKT,UKSP,TGHH,UMAD,UMSO,URVRSP,VICD,VRVR,VAGU,VEC,VEMA,VENX,AED,CHD,CKW,
CLB,CYF,DSD,ECB,EKW,EMSK,GOD,JLD,KCD,SBD,WDI,WFR,WKD,WPSL,WPVR,WSD,WSS,WZEN,XSD,YFF,YSW,BMW,NWF,
WAAA,WANZ,WAVR,WNZ,CWM,WO,ZMEN,PRIAN,ICRM,BEAF,ATYA,AJVR,DV,DVAJ,ADHN,MISM,OMT,EHM,SGKX,CADV,CRNX,
CSPL,EKDV,GEKI,MADM,MASE,MNSE,GZAP,GERK,KIWVR,KIWVRO,MMNM,ZUKO,SUMU,SNAP,CEAD,CEMD,CESD,CETD,DOPP,
MGHT,MOMJ,MOND,NTRD,SPRD,SKMN,TLSO,ALDN,DASD,DASS,DAZD,NTRH,DSVR,DAM,NSFS,NSPS,SBNS,NAMH,NNPJ,NPJB,
NPJS,PJAB,PJAM,HJBB,HJMO,INSTNA,HRSM,BBAN,BBSS,FUT,HAV,HAVD,HBA,HBAD,HHV,HRP,HRPD,HTD,HTDD,JMS,NTR,
PIYO,FGAN,EK,IZM,KPP,SM,SY,BANK,SAN,SBB,SMA,SMS,DPMI,KDMI,KMI,KYMI,MIBB,MIMA,LABY,LZAN,LZBS,LZDM,
LZDQ,LZPL,LZRT,LZSG,LZTD,LZWM,LZYL,RSRVR,OCVR,DSDP,MMB,MMPB,YMDD,YMDS,AVKH,MBYD,MDYD,MEVR,MEYD,MFYD,
MOHV,VTMN,FJIN,HALE,HALT,AGAV,AGEMIX,AGEOM,AGMX,ELEG,FEM,BABM,FKRU,KAGN,KAGP,MASM,MKON,GDRD,COGM,
TANP,TIKB,TIKP,BNST,TCHR,PKPL,BAB,ROOM,MOOR,MSTT,MMGH,DNJR,SOAN,SORA,SOTB,YMSR,HERK,NCYF,KTB,BLOR,
BDA,CKCK,MUCD,MUDR,MUFR,MUKA,MUKC,MUKD,AKB,MMND,BIJN,BINC,CLUB,STOL,HMN,HND,HNDB,HNDS,HNJC,HNKY,HNSE,
HNTV,HNVR,KRND,MIH,NSM,JERA,STSK,SMUK,SHIND,ORE,ORETD,OREC,ORECO,EMDS,MDS,MDSC,MDTE,MDTM,ONGP,NGKS,
MYBA,SOAV,SOON,HZGB,HZGD,SKMJ,DRPT,BOKO,AOZ,BBI,BEB,BIB,BID,CJOB,CJOD,CJVR,NSMD,OKB,OKK,OKL,OKP,OKS,
OKV,OKWD,OKX,OYJ,NGHJ,BKD,AILB,MRSS,FLAV,BOKD,LUCY,SGKI,MARR,MAAN,JIMMY,FAYS,T28,T38,HSKVR,PXVR,
PXVRW,SBGVR,KTDH,GKOK,KANO,DSAM
""".replace("\n", "").upper().split(","))

# [ko] 노이즈 제거 정규식 3종 — 그룹핑 로직 전체가 이 3개만으로 동작한다(방안 B: 정규식
#      필드 추출). 토큰 리스트를 만들지 않고 원본 문자열에 직접 re.sub를 적용하므로,
#      "토크나이저와 재조립 로직의 인덱스를 맞춰야 하는" 문제 자체가 존재하지 않는다.
#      각 정규식은 좌우에 문자/숫자가 아닌 경계를 요구해(lookaround) 단어 중간을
#      잘못 잘라내는 일이 없다.
# [en] The 3 noise-stripping regexes the entire grouping logic runs on (Option B: regex
#      field extraction). re.sub is applied directly to the raw string instead of
#      building a token list, so there's no "keep two splitters' indices in sync" problem
#      to begin with. Each regex requires a non-alnum boundary on both sides (lookaround)
#      so it never cuts a match out of the middle of an unrelated word.
_VARIABLE_PREFIX_ALT = "|".join(re.escape(p) for p in sorted(VARIABLE_PREFIXES, key=len, reverse=True))
VARIABLE_SEGMENT_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?:{_VARIABLE_PREFIX_ALT})[-_ ]?[A-Za-z0-9]{{1,4}}(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# [ko] 품번 패턴 하나로 "보호 식별자 판별"과 "미보호 순번 스트리핑"을 동시에 처리한다
#      (letters + 하이픈 유무 + digits 3~4자). 화이트리스트에 등록된 레이블이거나, 매치를
#      제거하고 남은 문자열에 공백 아닌 문자(제목/태그 등 컨텍스트)가 있으면 보호(그대로
#      유지), 그 외(=파일명이 사실상 코드 하나뿐인 경우)는 순번으로 보고 숫자만
#      제거한다 — 하이픈 유무 자체는 더 이상 보호 여부를 결정하지 않는다(v1.3). 이 판단
#      기준은 _is_protected_part_num() 하나로 통일되어 있어 "추출"과 "제거"가 서로 어긋날
#      수 없다. letters는 일반적으로 2~5자([A-Za-z]{2,5})이지만, KNOWN_LABEL_PREFIXES에
#      등록된 6자 이상 레이블(예: "AGEMIX")은 문자 그대로 대안에 추가해 하이픈 없이도
#      인식되게 한다 — 일반 2~5자 규칙 자체는 넓히지 않고, 딱 그 특정 등록 단어들만
#      예외로 둔다.
# [en] One pattern handles both "is this a protected identifier" and "strip this
#      unprotected sequence number" (letters + optional hyphen + digits 3-4 chars).
#      Protected means either the label is whitelisted, or removing the match leaves a
#      non-whitespace character behind (a title/tag — context); otherwise (the filename is
#      effectively just the bare code) it's a sequence number and only the digits are
#      dropped. A hyphen alone no longer decides protection (v1.3). The decision lives in
#      one place, _is_protected_part_num(), so extraction and stripping can never disagree.
#      "letters" is normally 2-5 chars ([A-Za-z]{2,5}), but KNOWN_LABEL_PREFIXES entries of
#      6+ chars (e.g. "AGEMIX") are added as literal alternatives so they're recognized
#      even without a hyphen — the generic 2-5 rule itself isn't widened, only those
#      specific registered words are carved out as an exception.
_LONG_LABEL_WORDS = sorted((p for p in KNOWN_LABEL_PREFIXES if len(p) > 5), key=len, reverse=True)
_PART_NUM_LETTERS_ALT = "|".join([r"[A-Za-z]{2,5}"] + [re.escape(w) for w in _LONG_LABEL_WORDS])
PART_NUM_RE = re.compile(rf"(?<![A-Za-z0-9])({_PART_NUM_LETTERS_ALT})(-?)([0-9]{{3,4}})(?![A-Za-z0-9])")

# [ko] 품번 바로 뒤, 파일명(stem) 맨 끝에 붙는 "영문자 1개(a-z/A-Z) + 언더바(들)" 조합은
#      업로더/썸네일 도구가 붙인 파생 변형 표시(예: 커버 이미지의 앞/뒤/보정 버전 구분용
#      v, r, c 등 단일 글자 접미사)일 뿐 품번의 일부가 아니므로 무시(제거)한다 — 예:
#      "MIHD009_", "MIHD009v", "MIHD009v_"는 모두 "MIHD009"와 같은 품번으로 취급.
#      PART_NUM_RE보다 먼저 적용해, 접미사를 뗀 뒤의 문자열을 그대로 PART_NUM_RE/화이트
#      리스트/컨텍스트 판정에 넘긴다(보호 여부 판단과는 완전히 독립적). 글자는 1개로
#      제한해 "AAA001BC"처럼 2자 이상 이어지는 진짜 접미사 텍스트까지 잘못 삼키지
#      않는다.
# [en] A "single letter (a-z/A-Z) + underscore(s)" combo glued directly after a part
#      number at the very end of the filename stem is just uploader/thumbnail-tool
#      variant noise (e.g. a single-letter front/back/retouch marker like v, r, c on a
#      cover image), not part of the code — e.g. "MIHD009_", "MIHD009v", and "MIHD009v_"
#      are all the same part number as "MIHD009". Applied before PART_NUM_RE so the
#      trimmed string flows into the normal PART_NUM_RE/whitelist/context decision
#      unchanged (independent of whether the code ends up protected or not). The letter
#      is capped at exactly one so a genuine 2+ character suffix (e.g. "AAA001BC") is
#      never swallowed by mistake.
PART_NUM_TRAILING_SUFFIX_RE = re.compile(
    rf"(?<![A-Za-z0-9])(({_PART_NUM_LETTERS_ALT})-?[0-9]{{3,4}})(?:[A-Za-z]_*|_+)$"
)

BRACKET_PAIRS = {"(": ")", "[": "]", "{": "}"}


def _has_context(s: str, span: tuple[int, int]) -> bool:
    """
    [ko] 매치(span)를 s에서 제거했을 때 공백이 아닌 문자가 남는지 여부. 파일명이
         "제목/태그 + 코드" 형태(컨텍스트 있음)인지, 코드 하나뿐인 단독 파일명(컨텍스트
         없음)인지 구별하는 데 쓰인다. 괄호는 이미 자리표시자로 마스킹된 상태로 들어오므로
         [제작사] 같은 태그만 있어도 컨텍스트로 인정된다.
    [en] Whether removing the match (span) from s leaves any non-whitespace character
         behind. Used to tell "title/tag + code" filenames (has context) apart from
         filenames that are effectively just the bare code (no context). Brackets arrive
         already masked as placeholders, so a bare tag like [제작사] still counts as context.
    """
    start, end = span
    return bool((s[:start] + s[end:]).strip())


def _is_protected_part_num(letters: str, has_context: bool) -> bool:
    """[ko] PART_NUM_RE 매치가 보호 식별자인지 판정하는 단일 기준. [en] The single source of truth for whether a PART_NUM_RE match is a protected identifier."""
    return letters.upper() in KNOWN_LABEL_PREFIXES or has_context


def _mask_bracket_groups(s: str) -> tuple[str, list[str]]:
    """
    [ko] (), [], {} 로 묶인 구간을 자리표시자로 치환해, 이후 노이즈 제거 정규식이 괄호
         안쪽 내용을 절대 건드리지 못하게 보호한다. 중첩 괄호도 깊이 계산으로 지원한다.
    [en] Replaces (), [], {} spans with placeholders so the later noise-stripping regexes
         can never reach inside them. Nested brackets are supported via depth counting.
    """
    saved: list[str] = []
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch in BRACKET_PAIRS:
            close = BRACKET_PAIRS[ch]
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                if s[j] == ch:
                    depth += 1
                elif s[j] == close:
                    depth -= 1
                j += 1
            saved.append(s[i:j])
            out.append(f"\x00{len(saved) - 1}\x00")
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out), saved


def _unmask_bracket_groups(s: str, saved: list[str]) -> str:
    """[ko] _mask_bracket_groups()가 심어둔 자리표시자를 원본 괄호 내용으로 되돌린다. [en] Restores the placeholders planted by _mask_bracket_groups() back to their original bracket content."""
    for idx, original in enumerate(saved):
        s = s.replace(f"\x00{idx}\x00", original)
    return s


def _extract_protected_id(stem: str) -> str | None:
    """
    [ko] stem에서 품번/식별 코드를 추출한다. 없으면 None.
         - 화이트리스트형: KNOWN_LABEL_PREFIXES에 등록된 레이블(예: "SONE100")은 하이픈
           유무나 컨텍스트와 무관하게 항상 보호.
         - 컨텍스트형: 화이트리스트에 없어도, 매치를 제거한 나머지 stem에 공백이 아닌
           문자(제목/태그 등)가 남아 있으면 보호. "AAA001"처럼 파일명이 사실상 코드
           하나뿐이면(컨텍스트 없음) 보호되지 않는다 — 순번과 품번을 문자열만으로 구별할
           수 없는 이 경우엔, 파일명 전체가 코드뿐인지가 유일한 판별 신호다.
    [en] Extracts a part-number/identifier code from a stem, or None if absent.
         - Whitelisted: a label registered in KNOWN_LABEL_PREFIXES (e.g. "SONE100") is
           always protected, regardless of a hyphen or context.
         - Contextual: even when not whitelisted, a match is protected if removing it from
           the stem leaves a non-whitespace character behind (a title/tag). When the
           filename is effectively just the bare code (e.g. "AAA001", no context), it's not
           protected — with no other signal to tell a sequence number from a real part
           number, whether the filename is nothing but the code is the only one available.
    """
    for m in PART_NUM_RE.finditer(stem):
        letters, digits = m.group(1), m.group(3)
        if _is_protected_part_num(letters, _has_context(stem, m.span())):
            return f"{letters.upper()}-{digits}"
    return None


def _strip_unprotected_part_num(m: re.Match) -> str:
    """[ko] 보호 대상이 아니면 숫자만 버리고 문자만 남긴다(예: "AAA001" -> "AAA"). 보호 대상이면 그대로 둔다. [en] Drops only the digits when unprotected (e.g. "AAA001" -> "AAA"); leaves a protected match untouched."""
    letters = m.group(1)
    if _is_protected_part_num(letters, _has_context(m.string, m.span())):
        return m.group(0)
    return letters


def _normalize_title(stem: str) -> str:
    """
    [ko]
    파일명 stem을 그룹핑 기준이자 그룹명이 되는 정규화된 제목으로 바꾼다. 순서대로
    3가지 노이즈만 제거한다(괄호 안쪽은 마스킹으로 보호돼 전혀 영향받지 않는다):
      1. 가변 구간(PART1, DISC_A 등) — 통째로 제거.
      2. 품번 바로 뒤, 파일명 맨 끝에 붙은 "영문자 1개 + 언더바(들)" 접미사(예:
         "MIHD009_", "MIHD009v", "MIHD009v_") — 품번의 일부가 아닌 파생 변형 표시이므로
         접미사만 제거하고 품번은 그대로 둔다(보호 여부 판단 전에 적용되어 판단 자체에는
         영향 없음).
      3. 미보호 순번(letters+3~4자리 숫자, 화이트리스트에도 없고 컨텍스트도 없음 — 즉
         파일명이 사실상 코드 하나뿐임) — 숫자만 제거, 문자는 유지.
    보호 식별자(화이트리스트형 또는 컨텍스트형)는 그대로 남으므로, 서로 다른 품번을 가진
    파일은 제목 텍스트 자체가 달라져 자연히 다른 그룹이 된다 — 유사도 점수나 별도의
    "거부" 단계 없이 완전일치 비교만으로 충분하다.

    [en]
    Turns a filename stem into the normalized title that is both the grouping key and
    the group name. Strips exactly 3 kinds of noise, in order (bracket interiors are
    masked and therefore completely unaffected):
      1. Variable segments (PART1, DISC_A, ...) — removed entirely.
      2. A "single letter + underscore(s)" suffix glued directly after a part number at
         the very end of the filename (e.g. "MIHD009_", "MIHD009v", "MIHD009v_") — a
         variant marker, not part of the code, so only the suffix is dropped and the code
         is left as-is (applied before the protection decision, so it never affects that
         decision).
      3. Unprotected sequence numbers (letters + 3-4 digits, not whitelisted and with no
         context — the filename is effectively just the code) — only the digits are
         dropped, the letters stay.
    A protected identifier (whitelisted or contextual) is left untouched, so files with
    different part numbers end up with different title text automatically — plain exact
    equality is enough, no similarity score or separate "reject" step needed.
    """
    masked, saved = _mask_bracket_groups(stem)
    masked = VARIABLE_SEGMENT_RE.sub("", masked)
    masked = PART_NUM_TRAILING_SUFFIX_RE.sub(r"\1", masked)
    masked = PART_NUM_RE.sub(_strip_unprotected_part_num, masked)
    title = _unmask_bracket_groups(masked, saved)
    title = re.sub(r"\s+", " ", title).strip()
    return title or stem


# [ko] 그룹핑/해시 핵심 로직 (GroupMD5.py에서 벤더링)
# [en] Core grouping/hashing logic (vendored from GroupMD5.py)

def get_truncated_filename_for_display(file_path: str, max_length: int = TRUNCATE_LENGTH) -> str:
    """
    [ko]
    tcbp._truncate_filename()에 위임한다 — len() 기반(코드포인트 개수)이 아니라
    전각 문자(한글/한자/가나 등)를 폭 2로 계산하는 화면 표시 폭 기준으로 자르므로,
    한글/일본어 파일명도 콘솔 폭을 넘기지 않는다.

    [en]
    Delegates to tcbp._truncate_filename() — truncates by on-screen display
    width (treating fullwidth characters like Hangul/Hanja/Kana as width 2)
    rather than len() (code point count), so Korean/Japanese filenames don't
    overflow the console width either.
    """
    return _truncate_filename(Path(file_path).name, max_length)


def detect_encoding(file_path: Path) -> str:
    try:
        with open(file_path, "rb") as f:
            raw_data = f.read(3)
            return "utf-8-sig" if raw_data.startswith(b"\xef\xbb\xbf") else "utf-8"
    except Exception:
        return "utf-8"


def calculate_md5(file_path: str, chunk_size: int,
                   progress_cb: Callable[[int, int], None] | None = None) -> str:
    """
    [ko]
    progress_cb는 청크를 읽을 때마다 호출하는 게 아니라 최대 PROGRESS_UPDATE_INTERVAL초에
    한 번만 호출한다(오리지널 GroupMD5.py의 refresh_per_second=0.67, 즉 약 1.5초
    간격과 동일) — 작은 chunk_size로 큰 파일을 처리할 때 매 청크마다 print()가
    호출되어 콘솔 출력이 병목이 되는 것을 방지한다. 단, 마지막 청크(완료 시점)는
    간격과 무관하게 항상 호출해 100%가 누락되지 않게 한다.

    [en]
    progress_cb is called at most once every PROGRESS_UPDATE_INTERVAL seconds,
    not on every chunk read (matches the original GroupMD5.py's
    refresh_per_second=0.67, i.e. about a 1.5-second interval) — this prevents
    print() from becoming a bottleneck when a small chunk_size is used against
    a large file. The final chunk (completion) always calls it regardless of
    the interval, so 100% is never skipped.
    """
    hash_md5 = hashlib.md5()
    total = os.path.getsize(file_path)
    done = 0
    last_update = 0.0
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hash_md5.update(chunk)
            done += len(chunk)
            if progress_cb:
                now = time.monotonic()
                if done >= total or now - last_update >= PROGRESS_UPDATE_INTERVAL:
                    progress_cb(done, total)
                    last_update = now
    return hash_md5.hexdigest()


def group_files_by_pattern(file_paths: list[str]) -> dict[str, list[str]]:
    """
    [ko] 파일들을 폴더별 + 정규화된 제목(_normalize_title) 완전일치 기준으로 그룹화한다.
         "얼마나 비슷한가"를 점수로 재는 대신, 알려진 노이즈(가변 구간/스타일/순번)만
         제거한 뒤 텍스트가 완전히 같은 파일끼리만 묶는다 — 서로 다른 보호 식별자를 가진
         파일은 _normalize_title() 단계에서 이미 텍스트 자체가 달라지므로 자연히 분리된다.
    [en] Groups files by folder plus exact match of the normalized title
         (_normalize_title). Instead of scoring "how similar", it strips only known
         noise (variable segments/style/sequence numbers) and groups files whose
         resulting text is identical — files with different protected identifiers
         already end up with different text at the _normalize_title() step, so they're
         naturally kept apart.
    """
    groups: dict[str, list[str]] = {}
    path_groups: dict[str, list[str]] = defaultdict(list)
    for file_path in file_paths:
        path_groups[str(Path(file_path).parent)].append(file_path)

    for dir_path, files in path_groups.items():
        dir_groups: dict[str, list[str]] = defaultdict(list)
        for fp in files:
            title = _normalize_title(Path(fp).stem)
            dir_groups[title].append(fp)
        for pattern, paths in dir_groups.items():
            groups[f"{dir_path}|{pattern}"] = paths

    return groups


def _sanitize_md5_filename(filename: str, base_dir: Path) -> str:
    """
    [ko] Windows에서 유효하도록 파일명을 정리하고, 경로 길이를 안전하게 제한한다.
    [en] Sanitize the filename to be valid on Windows and safely cap the total path length.
    """
    name, ext = os.path.splitext(filename)
    invalid = r'<>:"/\|?*'
    trans = str.maketrans({ch: " " for ch in invalid})
    safe_name = name.translate(trans)
    safe_name = "".join(ch for ch in safe_name if ord(ch) >= 32)
    safe_name = re.sub(r"\s+", " ", safe_name).strip().rstrip(".")

    candidate = f"{safe_name}{ext}"
    full_path = base_dir / candidate
    max_total = 240
    try:
        total_len = len(str(full_path))
    except Exception:
        total_len = 9999
    if total_len > max_total:
        digest = hashlib.md5(name.encode("utf-8", errors="ignore")).hexdigest()[:8]
        allowance = max(16, max_total - (len(str(base_dir)) + 1 + len(ext) + 1 + len(digest)))
        candidate = f"{safe_name[:allowance]}_{digest}{ext}"
    return candidate


def write_group_md5_file(dir_path: str, pattern: str, group_md5_data: list[tuple[str, str]],
                          use_bom: bool, log_fn: Callable[[str], None]) -> None:
    """
    [ko] 그룹의 MD5 목록을 .md5 파일로 쓴다. 실패 시 예외를 던진다(호출부가 집계).
    [en] Write the group's MD5 list to a .md5 file. Raises on failure (the caller tallies it).
    """
    md5_filename = f"{pattern}.md5" if pattern != "misc" else "files.md5"
    md5_filename = _sanitize_md5_filename(md5_filename, base_dir=Path(dir_path))
    md5_file_path = Path(dir_path) / md5_filename
    md5_file_path.parent.mkdir(parents=True, exist_ok=True)

    md5_content = [f"{md5_hash} *{Path(fp).name}" for md5_hash, fp in group_md5_data]
    encoding = "utf-8-sig" if use_bom else "utf-8"
    md5_file_path.write_text("\n".join(md5_content) + "\n", encoding=encoding)

    display_name = get_truncated_filename_for_display(str(md5_file_path))
    log_fn(f"created: {display_name} ({len(group_md5_data)} files)")


# [ko] 플러그인 핵심 로직 — run()과 단독 CLI가 공유
# [en] Core plugin logic — shared by run() and the standalone CLI

def _process(filelist: list[str], params: dict, log_fn: Callable[[str], None]) -> BatchResult:
    chunk_size = int(params.get("chunk_size", 64)) * 1024 * 1024
    use_bom = _to_bool(str(params.get("bom", "false")))
    succeeded: list[str] = []
    failed: list[str] = []

    try:
        log_fn(f"Num of files : {len(filelist)}")

        valid = [f for f in filelist if Path(f).exists()]
        valid_set = set(valid)
        missing = [f for f in filelist if f not in valid_set]
        for fp in missing:
            log_fn(f"skipped (no files): {get_truncated_filename_for_display(fp)}")
        failed.extend(missing)

        groups = group_files_by_pattern(valid)
        log_fn(f"Num of groups: {len(groups)}")
        total = len(valid)
        done = 0

        for group_key, group_files in groups.items():
            dir_path, pattern = group_key.split("|", 1)
            group_md5_data: list[tuple[str, str]] = []
            group_failed: list[str] = []
            group_total = len(group_files)

            for group_pos, fp in enumerate(group_files, 1):
                done += 1
                i, n, name = done, total, Path(fp).name
                # [ko] 진행률 줄에는 줄여서 표시하고, 실패 로그에는 원본 파일명을 그대로 남긴다
                #      (긴 파일명이 콘솔 폭을 넘겨 \r 진행률 줄이 깨지는 것을 방지 — 오리지널
                #      GroupMD5.py의 get_truncated_filename_for_display()와 동일한 방식).
                #      진행률 카운터는 전체 파일 카운터([i/n])와 현재 그룹 내 순번 카운터
                #      ([gp/gt])를 함께 표시한다.
                # [en] The progress line shows a truncated name; the failure log keeps the
                #      original filename as-is (prevents a long filename from wrapping the
                #      console and breaking the \r progress line — same approach as the
                #      original GroupMD5.py's get_truncated_filename_for_display()).
                #      The progress counter shows both the overall file counter ([i/n]) and
                #      the position within the current group ([gp/gt]).
                display_name = get_truncated_filename_for_display(fp)
                try:
                    h = calculate_md5(
                        fp, chunk_size,
                        progress_cb=lambda b, t, i=i, n=n, gp=group_pos, gt=group_total, name=display_name:
                            print(f"\r[{i}/{n}][{gp}/{gt}] {name:<{TRUNCATE_LENGTH}} {int(b * 100 / max(t, 1)):3d}%", end="", flush=True),
                    )
                    group_md5_data.append((h, fp))
                except Exception as e:
                    group_failed.append(fp)
                    log_fn(f"failed: {name} — {e}")
                finally:
                    # [ko] 파일별 진행률 \r 줄을 여기서 확정(개행)한다 — 그룹 루프가 끝난 뒤
                    #      한 번만 개행하면, 같은 그룹 내 다음 파일의 \r 진행률이 이전 파일의
                    #      줄을 그대로 덮어써 화면에서 사라져 버린다(예: 2개 파일 그룹에서
                    #      마지막 파일의 진행률만 보이고 첫 파일은 안 보이는 문제).
                    # [en] Finalize (newline) this file's \r progress line right here — if the
                    #      newline only happened once after the whole group loop, the next
                    #      file's \r progress in the same group would overwrite the previous
                    #      file's line in place, making it disappear from the screen (e.g., in
                    #      a 2-file group, only the last file's progress would ever be visible).
                    print()

            if group_md5_data:
                try:
                    write_group_md5_file(dir_path, pattern, group_md5_data, use_bom, log_fn)
                    succeeded.extend(fp for _, fp in group_md5_data)
                except Exception as e:
                    # [ko] 그룹 전체가 결국 아무 출력도 만들지 못했으므로 succeeded가 아니라 failed
                    # [en] The whole group ended up producing no output at all, so it goes to failed, not succeeded
                    group_failed.extend(fp for _, fp in group_md5_data)
                    log_fn(f"failed: entire {pattern}.md5 group ({len(group_md5_data)} files) — {e}")

            failed.extend(group_failed)
    finally:
        print()  # [ko] 중간에 죽거나 개행 없이 리턴하는 경우까지 포함해 개행을 보장 (10.5) / [en] guarantee a trailing newline even if it dies mid-way or returns without one

    return BatchResult(succeeded=succeeded, failed=failed)


@plugin(
    name="group_md5",
    contract_version="1.0",
    version="1.6",
    author="Magnum Choi",
    session_type="batch",
    requirements=[],
    notes_per_file=0,
)
def run(session: BatchSession) -> BatchResult:  # [ko] TCBP 진입점 / [en] TCBP entry point
    """
    [ko]
    run()의 예외는 catastrophic 신호로 예약되어 있다 (3.4/8.3.4) —
    PluginJobExecutor.run_batch()가 이를 filelist 전체 실패로 합성한다.
    여기서 삼키지 않는다 (_process 내부 try/finally는 개행 보장 전용).

    [en]
    An exception from run() is reserved as a catastrophic signal (3.4/8.3.4) —
    PluginJobExecutor.run_batch() synthesizes it into a full filelist failure.
    It is not swallowed here (the try/finally inside _process exists only to
    guarantee a trailing newline).
    """
    return _process(session.filelist, session.params, log_fn=lambda text: session.log(text, slot=0))


if __name__ == "__main__":  # [ko] 단독 CLI 진입점 (4.5) — 리스트 파일을 직접 읽는다 / [en] standalone CLI entry point (4.5) — reads the list file directly
    if len(sys.argv) < 2:
        print("Usage: python group_md5.py <list_file> [bom=true] [chunk_size=64]")
        raise SystemExit(1)
    list_path = Path(sys.argv[1])
    encoding = detect_encoding(list_path)
    lines = [line.strip() for line in list_path.read_text(encoding=encoding).splitlines() if line.strip()]
    base_dir = list_path.parent.resolve()
    files = [str(Path(line).resolve()) if Path(line).is_absolute() else str((base_dir / line).resolve())
             for line in lines]

    cli_params = parse_params(sys.argv[2:])
    result = _process(files, cli_params, log_fn=print)
    print(f"succeeded={len(result.succeeded)} failed={len(result.failed)}")
    raise SystemExit(0 if not result.failed else 1)
