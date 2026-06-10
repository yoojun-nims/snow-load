# =============================================================================
#  최대가능적설하중 산출 코드
#  기반자료: 기상청 ASOS 시간자료 (97개 지점)
#
#  산출 유형:
#    유형 A (97개소): 레이저식 적설계 + 무게식강수량계
#    유형 B (24개소): 레이저식 적설계 + 무게식강수량계 + 적설판
#
#  ※ 현 단계: ASOS 자료로 SWE_gauge, HS_laser, HS_board 대용
#    향후 실측 장비 자료로 대체 예정
#
#  참고문헌: 이영규 외(2015), 한국방재학회논문집 Vol.15 No.1
# =============================================================================

import pandas as pd
import glob
import os

# =============================================================================
#  분석 설정
# =============================================================================

# ── 분석 기간 (이 부분만 수정하여 기간 변경) ──────────────────────────────
START_DATE = "202411260000"   # 시작시각 (YYYYMMDDHHMI)
END_DATE   = "202411292300"   # 끝시각   (YYYYMMDDHHMI)

# ── 경로 설정 ─────────────────────────────────────────────────────────────
BASE_DIR = r"E:\SNOW\API_DATA\HOUR"

# ── 적설판식 관측 지점 목록 (24개소) ─────────────────────────────────────
#   SD_HR3(3시간 신적설), SD_DAY(일 신적설) 직접 관측 지점
BOARD_STNS = {
    93, 102, 104, 108, 112, 115, 119, 131, 133, 136,
   138, 143, 146, 152, 155, 156, 159, 165, 168, 169,
   177, 184, 189, 298
}

# ── 결측값 코드 (ASOS 공통) ───────────────────────────────────────────────
MISSING_VALUES = [-9, -9.0, -99.0, -999.0]

# ── 눈밀도 물리적 허용 범위 (선행연구 기준) ───────────────────────────────
RHO_MIN = 50    # kg/m³  (건조·가벼운 신적설 하한)
RHO_MAX = 500   # kg/m³  (압밀된 오래된 눈 상한)


# =============================================================================
#  STEP 1. 데이터 로딩 및 전처리
# =============================================================================

start_dt   = pd.to_datetime(START_DATE, format="%Y%m%d%H%M")
end_dt     = pd.to_datetime(END_DATE,   format="%Y%m%d%H%M")
date_range = pd.date_range(start=start_dt.date(), end=end_dt.date(), freq="D")

print("=" * 60)
print("  STEP 1. 데이터 로딩 및 전처리")
print("=" * 60)
print(f"  분석 기간: {start_dt} ~ {end_dt}")
print(f"  대상 날짜: {len(date_range)}일")
print("=" * 60)

# ── 1-1. 파일 목록 수집 ───────────────────────────────────────────────────
all_files = []
for dt in date_range:
    folder = os.path.join(BASE_DIR, dt.strftime("%Y%m"), dt.strftime("%d"))
    if not os.path.exists(folder):
        print(f"  [경고] 폴더 없음: {folder}")
        continue
    files = sorted(glob.glob(os.path.join(folder, "*.csv")))
    print(f"  [{dt.strftime('%Y.%m.%d')}] 파일 수: {len(files)}개")
    all_files.extend(files)

print(f"\n  총 파일 수: {len(all_files)}개")

# ── 1-2. 파일 로딩 ────────────────────────────────────────────────────────
all_dfs = []
for f in all_files:
    try:
        df = pd.read_csv(f, encoding="cp949")
        all_dfs.append(df)
    except Exception as e:
        print(f"  [오류] {os.path.basename(f)}: {e}")

print(f"  로딩 성공: {len(all_dfs)}개")

if len(all_dfs) == 0:
    raise SystemExit(f"파일 로딩 실패 - 경로를 확인하세요: {BASE_DIR}")

df_raw = pd.concat(all_dfs, ignore_index=True)

# ── 1-3. 기본 전처리 ──────────────────────────────────────────────────────
# 시각 파싱
df_raw["TM"] = pd.to_datetime(
    df_raw["TM"].astype(str), format="%Y%m%d%H%M", errors="coerce"
)

# 분석 기간 필터링
df_raw = df_raw[(df_raw["TM"] >= start_dt) & (df_raw["TM"] <= end_dt)].copy()

# 수치형 변환
str_cols = ["WW", "CT"]
num_cols = [col for col in df_raw.columns if col not in ["TM"] + str_cols]
for col in num_cols:
    df_raw[col] = pd.to_numeric(df_raw[col], errors="coerce")

# 결측코드 → NaN
df_raw.replace(MISSING_VALUES, float("nan"), inplace=True)

# 정렬
df_raw = df_raw.sort_values(["TM", "STN"]).reset_index(drop=True)

# ── 1-4. 누락 시간 자동 생성 ─────────────────────────────────────────────
full_time = pd.date_range(start=start_dt, end=end_dt, freq="h")
all_stns  = sorted(df_raw["STN"].dropna().unique().astype(int))

grid   = pd.MultiIndex.from_product([full_time, all_stns], names=["TM", "STN"])
df_all = pd.merge(
    pd.DataFrame(index=grid).reset_index(),
    df_raw, on=["TM", "STN"], how="left"
)

# ── 1-5. 변수별 결측 처리 (IR 코드 기반) ─────────────────────────────────
# RN: IR=3(무강수확인) → 0,  IR=4(결측) → NaN 유지
df_all.loc[df_all["IR"] == 3, "RN"] = 0.0

# SD_HR3: RN>0 이고 SD_HR3=NaN → 0 (비가 왔으나 적설 없음)
df_all.loc[(df_all["RN"] > 0) & (df_all["SD_HR3"].isna()), "SD_HR3"] = 0.0

# ── 1-6. STEP 1 결과 확인 ────────────────────────────────────────────────
print(f"\n  데이터 크기: {len(df_all):,}행 × {len(df_all.columns)}열")
print(f"  예상 행수  : {len(full_time)}시간 × {len(all_stns)}지점"
      f" = {len(full_time)*len(all_stns):,}행"
      f"  {'✅' if len(df_all)==len(full_time)*len(all_stns) else '❌'}")
print(f"  관측 지점  : {df_all['STN'].nunique()}개")
print(f"  시각 범위  : {df_all['TM'].min()} ~ {df_all['TM'].max()}")

print("\n  STEP 1 완료!")


# =============================================================================
#  STEP 2. 변수 준비
#  - 단위 통일: cm → mm
#  - 방법론 변수명으로 컬럼 생성
#  - SWE_gauge 누적값 계산 (지점별)
# =============================================================================

print("\n" + "=" * 60)
print("  STEP 2. 변수 준비 (단위 통일 mm + SWE 누적 계산)")
print("=" * 60)

# ── 2-1. 단위 변환 및 변수명 매핑 ────────────────────────────────────────
#
#   ASOS 컬럼    →  방법론 변수     단위 변환
#   RN(mm)       →  SWE_3h(mm)      그대로 (3시간 강수량 = 3시간 SWE 증분)
#   SD_HR3(cm)   →  HN_3h(mm)       × 10
#   SD_DAY(cm)   →  HN_day(mm)      × 10
#   SD_TOT(cm)   →  HS_tot(mm)      × 10  (HS_board = HS_laser 대용)

df_all["SWE_3h"]  = df_all["RN"]                # 3시간 강수량 = 3시간 SWE 증분 (mm)
df_all["HN_3h"]   = df_all["SD_HR3"] * 10    # cm → mm
df_all["HN_day"]  = df_all["SD_DAY"]  * 10   # cm → mm
df_all["HS_tot"]  = df_all["SD_TOT"]  * 10   # cm → mm (HS_board = HS_laser 대용)

# ── 2-2. SWE_gauge 누적값 계산 (지점별 시간 순 누적합) ───────────────────
#
#   SWE_cum(t) = Σ SWE_3h(i)   (i: 분석 시작 ~ t)
#
#   ※ SWE_3h가 NaN인 경우 → 누적에서 제외 (0으로 간주하지 않음)
#      → fillna(0)는 결측을 무강수로 가정하므로 주의
#      → 현 단계에서 NaN → 0으로 채운 후 누적 (보수적 처리)
#        향후 결측 구간 보간 로직 추가 가능

df_all = df_all.sort_values(["STN", "TM"]).reset_index(drop=True)

df_all["SWE_cum"] = (
    df_all.groupby("STN")["SWE_3h"]
    .transform(lambda x: x.fillna(0).cumsum())
)
# NaN이었던 구간은 누적이 되더라도 실제 강수 없는 것으로 표시 유지
# (향후 품질 관리 로직 추가 가능)

# ── 2-3. 결과 확인 ───────────────────────────────────────────────────────
print("\n── 변수 준비 현황 ────────────────────────────────────")
vars_check = {
    "SWE_3h  : 3시간 강수량=SWE 증분 (mm)" : "SWE_3h",
    "SWE_cum : 누적 SWE (mm)"             : "SWE_cum",
    "HN_3h   : 3시간 신적설 (mm)"         : "HN_3h",
    "HN_day  : 일 신적설 (mm)"            : "HN_day",
    "HS_tot  : 누적 적설깊이 (mm)"        : "HS_tot",
}
for label, col in vars_check.items():
    n_valid = df_all[col].notna().sum()
    n_pos   = (df_all[col] > 0).sum()
    print(f"  {label:<35} 유효: {n_valid:,}행  (>0: {n_pos:,}행)")

print("\n── 지점별 SWE_cum 최대값 상위 10개 ──────────────────")
swe_max = (
    df_all.groupby("STN")["SWE_cum"].max()
    .sort_values(ascending=False)
    .head(10)
    .reset_index()
)
swe_max.columns = ["STN", "SWE_cum_max(mm)"]
print(swe_max.to_string(index=False))

print("\n  STEP 2 완료!")


# =============================================================================
#  STEP 3. 눈밀도(ρ_snow) 산출
#
#  [공통] ρ_snow  = [SWE_cum(mm) / HS_tot(mm)] × 1000      (kg/m³)
#
#  [유형 A] Δρ_A   = [SWE_3h(mm) / ΔHS_tot(mm)] × 1000    (kg/m³)
#    - ΔHS_tot(mm) = HS_tot(t) - HS_tot(t-3h)  ← 3시간 적설깊이 변화량
#
#  [유형 B] Δρ_3h    = [SWE_3h(mm) / HN_3h(mm)] × 1000         (kg/m³) ← 우선
#           Δρ_event = [SWE_event_board / HN_3h_event_cum] × 1000 (kg/m³) ← 대체 (이벤트 누적)
#           Δρ_day   = [SWE_day(mm) / HN_day(mm)] × 1000         (kg/m³) ← 참고용
#    - SWE_day(mm) = SWE_cum(t) - SWE_cum(당일 00시)
#
#  물리적 허용 범위: 50 ~ 500 kg/m³ (이영규 외 2015)
# =============================================================================

print("\n" + "=" * 60)
print("  STEP 3. 눈밀도(ρ_snow) 산출")
print("=" * 60)

# ── 3-1. 유형 A용 보조 변수: 3시간 적설깊이 변화량 ──────────────────────
#
#   유형 A는 적설판이 없으므로 레이저 적설계의 3시간 변화량으로
#   신적설 깊이를 대체함
#
#   hs_chg_3h(mm) = HS_tot(t) - HS_tot(t-3h)
#   → 1시간 간격 데이터에서 지점별 3행 이전 값 참조

df_all["hs_prev_3h"] = df_all.groupby("STN")["HS_tot"].shift(3)  # 3시간 전 적설깊이
df_all["hs_chg_3h"]  = df_all["HS_tot"] - df_all["hs_prev_3h"]   # 3시간 적설깊이 변화량


# ── 3-2. 유형 B용 보조 변수: 당일 누적 SWE ──────────────────────────────
#
#   유형 B는 일 신적설판(HN_day)이 있으므로 같은 구간(00시~현재)의
#   SWE 증분을 대응시켜 일 신적설밀도를 산출함
#
#   SWE_day(mm) = SWE_cum(t) - SWE_cum(당일 00시)

df_all["date"] = df_all["TM"].dt.date

swe_at_midnight = (
    df_all[df_all["TM"].dt.hour == 0]
    .set_index(["STN", "date"])["SWE_cum"]
    .rename("swe_at_midnight")
)
df_all = df_all.join(swe_at_midnight, on=["STN", "date"])
df_all["SWE_day"] = df_all["SWE_cum"] - df_all["swe_at_midnight"]


# ── 3-3. 공통: 기존적설 눈밀도(rho_exist) ────────────────────────────────
#
#   현재 쌓여 있는 눈 전체의 유효밀도
#   (유형A: SWE_cum/HS_laser,  유형B: SWE_cum/HS_board)
#
#   rho_exist(kg/m³) = [SWE_cum(mm) / HS_tot(mm)] × 1000
#
#   계산 조건: SWE_cum > 0  AND  HS_tot > 0

mask_exist = (df_all["SWE_cum"] > 0) & (df_all["HS_tot"] > 0)

df_all["rho_exist"] = float("nan")   # 기존적설 유효밀도 (kg/m³)
df_all.loc[mask_exist, "rho_exist"] = (
    df_all.loc[mask_exist, "SWE_cum"] / df_all.loc[mask_exist, "HS_tot"]
) * 1000


# ── 3-4. 레이저식: 신적설밀도(rho_new_laser_3h) ─────────────────────────────
#
#   분자: SWE_3h        — 무게식 강수량계로 측정한 3시간 적설수량 (mm)
#   분모: hs_chg_3h     — 레이저 적설계의 3시간 전체 적설 깊이 변화량
#                         = HS(t) − HS(t−3h)  (mm)
#
#   rho_new_laser_3h(kg/m³) = [SWE_3h(mm) / hs_chg_3h(mm)] × 1000
#
#   ※ 분모의 한계 (적설판 HN_3h 대비):
#      hs_chg_3h 는 신적설 깊이를 직접 측정하지 않고,
#      전체 적설 깊이의 변화량으로 간접 산출함.
#      신적설이 쌓이는 동시에 기존 적설층이 침강(compaction)되면
#        hs_chg_3h < 실제 신적설 깊이  →  rho_new_laser_3h 과대 추정 가능
#      반면 적설판 HN_3h 는 신적설만 직접 포착하므로 더 정확.
#      이로 인해 적설판 지점에서는 rho_new_board_3h 를 우선 적용.
#
#   계산 조건: SWE_3h > 0  AND  hs_chg_3h >= MIN_HS_CHG
#
#   hs_chg_3h ≤ 0       : 눈이 줄었거나 변화 없음 → 계산 제외
#   hs_chg_3h < 10 mm   : 레이저 적설계 측정 불확도(±10 mm) 이하 → 신호/노이즈 구분
#                          불가, 비율 불안정 → 계산 제외
#                          (예: SWE_3h=0.9 mm / hs_chg_3h=2 mm → 450 kg/m³ 비정상)
#   → 제외된 시각은 rho_new_event_laser 또는 rho_exist 로 자동 대체
#
#   ※ 참고: Kochendorfer et al.(2017), WMO(2018) — 자동기상관측 적설 측정
#            불확도 기준 ±10 mm 적용

MIN_HS_CHG = 10.0  # mm — 레이저 측정 불확도 기반 최소 유효 깊이 변화 임계값

mask_laser = (df_all["SWE_3h"] > 0) & (df_all["hs_chg_3h"] >= MIN_HS_CHG)

df_all["rho_new_laser_3h"] = float("nan")   # 레이저식 신적설밀도 (kg/m³)
df_all.loc[mask_laser, "rho_new_laser_3h"] = (
    df_all.loc[mask_laser, "SWE_3h"] / df_all.loc[mask_laser, "hs_chg_3h"]
) * 1000


# ── 3-5. 적설판식: 신적설밀도(rho_new_board_3h, rho_new_board_day) ────────
#
#   적설판 직접 관측값(HN_3h, HN_day)으로 신적설 깊이를 사용
#   (레이저 변화량보다 더 정확한 신적설 깊이 측정 가능)
#
#   rho_new_board_3h(kg/m³)  = [SWE_3h(mm) / HN_3h(mm)] × 1000      ← 우선 적용
#   rho_new_board_day(kg/m³) = [SWE_day(mm) / HN_day(mm)] × 1000    ← 참고용 (일 기준)
#
#   ※ 최종 우선순위(rho_new_board):
#      rho_new_board_3h → rho_new_event_board → rho_exist
#      rho_new_event_board는 STEP 3-E에서 산출 → 최종 combine은 STEP 3-E 완료 후 적용
#
#   계산 조건:
#     rho_new_board_3h  : SWE_3h > 0   AND  HN_3h >= MIN_HN_3H
#     rho_new_board_day : SWE_day > 0  AND  HN_day > 0  (참고용)
#
#   HN_3h < 10 mm : 적설판 측정 불확도 수준 → 밀도 비율 불안정, 계산 제외
#                   레이저 MIN_HS_CHG 와 동일 기준 적용 (일관성)

MIN_HN_3H = 10.0   # mm — 적설판 신적설밀도 산출 최소 신적설 임계값

mask_board_3h  = (df_all["SWE_3h"] > 0) & (df_all["HN_3h"] >= MIN_HN_3H)
mask_board_day = (df_all["SWE_day"] > 0) & (df_all["HN_day"] > 0)

df_all["rho_new_board_3h"]  = float("nan")   # 적설판식 신적설밀도, 3시간판 (kg/m³)
df_all["rho_new_board_day"] = float("nan")   # 적설판식 신적설밀도, 일적설판 (kg/m³)

df_all.loc[mask_board_3h, "rho_new_board_3h"] = (
    df_all.loc[mask_board_3h, "SWE_3h"] / df_all.loc[mask_board_3h, "HN_3h"]
) * 1000

df_all.loc[mask_board_day, "rho_new_board_day"] = (
    df_all.loc[mask_board_day, "SWE_day"]
    / df_all.loc[mask_board_day, "HN_day"]
) * 1000

# rho_new_board_3h만 우선 저장 (이벤트 기반 대체는 STEP 3-E 완료 후 적용)
# 최종 우선순위: rho_new_board_3h → rho_new_event_board → rho_exist
df_all["rho_new_board"] = df_all["rho_new_board_3h"].copy()


# ── 3-6. 물리적 이상값 제거 ───────────────────────────────────────────────
#
#   [공통 범위] 50 ~ 500 kg/m³ : rho_exist 포함 모든 밀도 컬럼
#     RHO_MIN =  50 kg/m³ (건조 신설 하한)
#     RHO_MAX = 500 kg/m³ (압밀·오래된 눈 상한)
#
#   [신설 전용 상한] 50 ~ 300 kg/m³ : rho_new_*_3h (3시간 신적설 밀도)
#     건조 신설  :  50–150 kg/m³
#     습윤 신설  : 150–300 kg/m³
#     300 초과   : 신설이 아닌 기존 적설 변질층 → 신설 밀도로 부적합
#     ※ Roebber et al.(2003), Judson & Doesken(2000) 신설 밀도 범위 참고
#
#   이중 필터(① 최소 깊이 임계값 + ② 신설 밀도 상한)로 비정상값 차단

RHO_NEW_MAX = 300  # kg/m³ — 신설 밀도 물리 상한 (습윤 신설 최대)

# ① 공통 필터 (50 ~ 500 kg/m³)
rho_cols_common = [
    "rho_exist",
    "rho_new_board_day",
    "rho_new_board",
]
for col in rho_cols_common:
    out = df_all[col].notna() & (
        (df_all[col] < RHO_MIN) | (df_all[col] > RHO_MAX)
    )
    df_all.loc[out, col] = float("nan")

# ② 신설 전용 필터 (50 ~ 300 kg/m³) — 3시간 신적설 밀도
rho_cols_new = [
    "rho_new_laser_3h",
    "rho_new_board_3h",
]
for col in rho_cols_new:
    out = df_all[col].notna() & (
        (df_all[col] < RHO_MIN) | (df_all[col] > RHO_NEW_MAX)
    )
    df_all.loc[out, col] = float("nan")


# ── 3-7. 결과 확인 출력 ──────────────────────────────────────────────────

def rho_summary(df, col, label):
    n   = df[col].notna().sum()
    mn  = df[col].min()  if n > 0 else float("nan")
    avg = df[col].mean() if n > 0 else float("nan")
    mx  = df[col].max()  if n > 0 else float("nan")
    print(f"  {label:<45} 유효:{n:>4}행  "
          f"min={mn:6.1f}  mean={avg:6.1f}  max={mx:6.1f}  kg/m³")

print("\n── 눈밀도 산출 결과 ──────────────────────────────────────────")
print("  " + "-" * 75)
rho_summary(df_all, "rho_exist",
            "rho_exist        [공통]  기존적설 유효밀도")
rho_summary(df_all, "rho_new_laser_3h",
            "rho_new_laser_3h    [레이저식] 3h변화량 기반 신적설밀도")
rho_summary(df_all, "rho_new_board_3h",
            "rho_new_board_3h [적설판식] 3시간판 기반 신적설밀도")
rho_summary(df_all, "rho_new_board_day",
            "rho_new_board_day[적설판식] 일적설판 기반 신적설밀도")
rho_summary(df_all, "rho_new_board",
            "rho_new_board    [적설판식] 우선순위 적용 최종값")

print("\n── 적설판식 신적설밀도 현황 (STEP 3 기준) ──────────────────")
n_3h  = df_all["rho_new_board_3h"].notna().sum()
n_day = df_all["rho_new_board_day"].notna().sum()
print(f"  rho_new_board_3h  (3시간판, 우선)       : {n_3h:>4}행")
print(f"  rho_new_board_day (일적설판, 참고용)    : {n_day:>4}행")
print(f"  ※ 이벤트 기반 대체(rho_new_event_board)는 STEP 3-E 후 최종 combine 적용")

print("\n── 눈밀도 유효값 미리보기 (상위 5행) ────────────────────────")
cols_show = ["TM", "STN", "TA",
             "SWE_3h", "hs_chg_3h", "HN_3h", "HS_tot",
             "rho_exist", "rho_new_laser_3h", "rho_new_board_3h"]
df_rho = df_all[
    df_all["rho_exist"].notna() | df_all["rho_new_laser_3h"].notna()
]
if len(df_rho) > 0:
    print(df_rho[cols_show].head(5).to_string(index=False))
else:
    print("  눈밀도 산출 결과 없음")

print("\n  STEP 3 완료!")


# =============================================================================
#  STEP 3-E. 이벤트 기반 누적변수 및 눈밀도 산출 (지점별)
#
#  ■ 이벤트 트리거 기준 — 지점 유형별 분리
#    레이저식 (97개소): hs_chg_3h > 0  ← 레이저 적설계가 적설 증가를 감지한 시점
#    적설판식 (24개소): HN_3h    > 0  ← 적설판이 신적설을 직접 관측한 시점
#
#  ■ 이벤트 종료 기준
#    GAP_HOURS 시간 이상 트리거값 = 0 (또는 NaN) → 이벤트 종료
#    다음 트리거 발생 → 새 이벤트 시작 (event_id 증가), 지점별 독립 부여
#
#  ■ 레이저 이벤트 변수 (97개소)
#    event_id_laser       : 레이저 이벤트 번호 (0=이벤트 외)
#    swe_at_estart_laser  : 레이저 이벤트 시작 직전 SWE_cum (mm)
#    hs_at_estart_laser   : 레이저 이벤트 시작 시점 HS_tot (mm) ← 기존적설 기준점
#    SWE_event_laser      : 레이저 이벤트 누적 SWE = SWE_cum - swe_at_estart_laser (mm)
#    HS_laser_event_cum   : 레이저 이벤트 적설깊이 변화 = HS_tot - hs_at_estart_laser (mm)
#
#  ■ 적설판 이벤트 변수 (24개소)
#    event_id_board       : 적설판 이벤트 번호 (0=이벤트 외)
#    swe_at_estart_board  : 적설판 이벤트 시작 직전 SWE_cum (mm)
#    SWE_event_board      : 적설판 이벤트 누적 SWE = SWE_cum - swe_at_estart_board (mm)
#    HN_3h_event_cum      : 적설판 이벤트 누적 HN_3h = Σ HN_3h (이벤트 시작~현재) (mm)
#
#  ■ 이벤트 기반 신적설밀도
#    rho_new_event_laser : SWE_event_laser / HS_laser_event_cum × 1000  (레이저식)
#    rho_new_event_board : SWE_event_board / HN_3h_event_cum    × 1000  (적설판식)
#
#  ■ 적설판식 최종 우선순위 (STEP 3-E 완료 후 combine)
#    rho_new_board = rho_new_board_3h → rho_new_event_board → (STEP 4에서 rho_exist)
# =============================================================================

print("\n" + "=" * 60)
print("  STEP 3-E. 이벤트 기반 누적변수 및 눈밀도 산출")
print("=" * 60)

# ── 이벤트 구분 기준 (조정 가능) ─────────────────────────────────────────
#
#   GAP_HOURS_LASER = 6 : 레이저식 (1시간 관측)
#     → 6시간 연속으로 hs_chg_3h = 0 이면 이벤트 종료
#
#   GAP_HOURS_BOARD = 9 : 적설판식 (3시간 간격 관측)
#     → HN_3h는 3시간마다 관측, 관측 사이 2시간은 항상 NaN(비활성)
#     → 9시간 = 3시간 관측 기준 3번 연속 무강수 → 이벤트 종료
#     → 6시간으로 설정 시 실질적으로 2번 연속 무강수에 종료되어 이벤트 과다 분리 우려

GAP_HOURS_LASER = 6   # 레이저식 이벤트 종료 기준 (시간)
GAP_HOURS_BOARD = 9   # 적설판식 이벤트 종료 기준 (시간, 3h 관측간격 × 3회)

def assign_event_id(series, gap_hours):
    """
    시계열 series > 0 를 트리거로 이벤트 ID를 부여하는 범용 함수.
    - 트리거 발생 전 gap_hours 시간 이상 연속 비발생 → 새 이벤트
    - 비발생 시간은 event_id = 0 (이벤트 외)
    """
    active = (series > 0).fillna(False)
    past_all_inactive = (
        (~active)
        .shift(1)
        .rolling(gap_hours, min_periods=gap_hours)
        .min()
        .fillna(1)
        .astype(bool)
    )
    new_event = active & past_all_inactive
    return new_event.cumsum().where(active, 0)

# ── 3-E-1. 레이저 이벤트 ID 부여 (97개소, hs_chg_3h 기준) ───────────────
#   hs_chg_3h > 0: 레이저 적설계가 3시간 전 대비 적설 증가 감지
#   GAP_HOURS_LASER = 6시간

df_all["event_id_laser"] = (
    df_all.groupby("STN")["hs_chg_3h"]
    .transform(lambda x: assign_event_id(x, GAP_HOURS_LASER))
    .astype(int)
)

# ── 3-E-2. 적설판 이벤트 ID 부여 (24개소, HN_3h 기준) ───────────────────
#   HN_3h > 0: 적설판이 3시간 신적설 직접 관측
#   GAP_HOURS_BOARD = 9시간 (3h 관측간격 × 3회 연속 무강수)
#   24개소 외 지점은 0 유지

df_all["event_id_board"] = 0

board_event_series = (
    df_all[df_all["STN"].isin(BOARD_STNS)]
    .groupby("STN")["HN_3h"]
    .transform(lambda x: assign_event_id(x, GAP_HOURS_BOARD))
    .astype(int)
)
df_all.loc[df_all["STN"].isin(BOARD_STNS), "event_id_board"] = board_event_series

# ── 3-E-3. 레이저 이벤트 기준값 추출 ────────────────────────────────────
#   이벤트 첫 행 기준:
#   swe_at_estart_laser = SWE_cum(첫행) - SWE_3h(첫행)  ← 이벤트 직전 누적값
#   hs_at_estart_laser  = HS_tot(첫행)                   ← 이벤트 시작 적설깊이

laser_event_rows = df_all[df_all["event_id_laser"] > 0]
laser_ref = (
    laser_event_rows
    .groupby(["STN", "event_id_laser"])
    .first()[["SWE_cum", "SWE_3h", "HS_tot"]]
)
laser_ref["swe_at_estart_laser"] = laser_ref["SWE_cum"] - laser_ref["SWE_3h"].fillna(0)
laser_ref["hs_at_estart_laser"]  = laser_ref["HS_tot"]
laser_ref = laser_ref[["swe_at_estart_laser", "hs_at_estart_laser"]]

df_all = df_all.join(laser_ref, on=["STN", "event_id_laser"])

# 레이저 이벤트 누적변수
df_all["SWE_event_laser"]    = df_all["SWE_cum"] - df_all["swe_at_estart_laser"]
df_all["HS_laser_event_cum"] = df_all["HS_tot"]  - df_all["hs_at_estart_laser"]

# 이벤트 외 또는 음수(눈 녹음) 구간 NaN 처리
df_all.loc[df_all["event_id_laser"] == 0,
           ["SWE_event_laser", "HS_laser_event_cum"]] = float("nan")
df_all.loc[df_all["HS_laser_event_cum"] < 0, "HS_laser_event_cum"] = float("nan")

# ── 3-E-4. 적설판 이벤트 기준값 추출 ────────────────────────────────────
#   swe_at_estart_board = SWE_cum(첫행) - SWE_3h(첫행)  ← 이벤트 직전 누적값

board_event_rows = df_all[df_all["event_id_board"] > 0]
board_ref = (
    board_event_rows
    .groupby(["STN", "event_id_board"])
    .first()[["SWE_cum", "SWE_3h"]]
)
board_ref["swe_at_estart_board"] = board_ref["SWE_cum"] - board_ref["SWE_3h"].fillna(0)
board_ref = board_ref[["swe_at_estart_board"]]

df_all = df_all.join(board_ref, on=["STN", "event_id_board"])

# 적설판 이벤트 누적 SWE
df_all["SWE_event_board"] = df_all["SWE_cum"] - df_all["swe_at_estart_board"]
df_all.loc[df_all["event_id_board"] == 0, "SWE_event_board"] = float("nan")

# 적설판 이벤트 내 HN_3h 누적합
#   HN_3h는 3시간 증분값 → 이벤트 시작부터 단순 cumsum
df_all["HN_3h_event_cum"] = float("nan")
board_mask_event = df_all["STN"].isin(BOARD_STNS) & (df_all["event_id_board"] > 0)

df_all.loc[board_mask_event, "HN_3h_event_cum"] = (
    df_all[board_mask_event]
    .groupby(["STN", "event_id_board"])["HN_3h"]
    .transform(lambda x: x.fillna(0).cumsum())
)

# ── 3-E-5. 이벤트 기반 신적설밀도 ───────────────────────────────────────
#
#   [레이저식] rho_new_event_laser = SWE_event_laser / HS_laser_event_cum × 1000
#     트리거: hs_chg_3h > 0 (레이저 적설 증가 감지)
#     분자  : SWE_event_laser (레이저 이벤트 시작 이후 누적 강수)
#     분모  : HS_laser_event_cum (레이저 이벤트 시작 이후 적설깊이 변화)
#
#   [적설판식] rho_new_event_board = SWE_event_board / HN_3h_event_cum × 1000
#     트리거: HN_3h > 0 (적설판 신적설 직접 관측)
#     분자  : SWE_event_board (적설판 이벤트 시작 이후 누적 강수)
#     분모  : HN_3h_event_cum (적설판 이벤트 시작 이후 누적 신적설)

mask_event_laser = (
    (df_all["event_id_laser"] > 0)
    & (df_all["SWE_event_laser"] > 0)
    & (df_all["HS_laser_event_cum"] > 0)
)
df_all["rho_new_event_laser"] = float("nan")
df_all.loc[mask_event_laser, "rho_new_event_laser"] = (
    df_all.loc[mask_event_laser, "SWE_event_laser"]
    / df_all.loc[mask_event_laser, "HS_laser_event_cum"]
) * 1000

mask_event_board = (
    df_all["STN"].isin(BOARD_STNS)
    & (df_all["event_id_board"] > 0)
    & (df_all["SWE_event_board"] > 0)
    & (df_all["HN_3h_event_cum"] > 0)
)
df_all["rho_new_event_board"] = float("nan")
df_all.loc[mask_event_board, "rho_new_event_board"] = (
    df_all.loc[mask_event_board, "SWE_event_board"]
    / df_all.loc[mask_event_board, "HN_3h_event_cum"]
) * 1000

# ── 3-E-6. 이상값 제거 (50 ~ 500 kg/m³) ─────────────────────────────────
for col in ["rho_new_event_laser", "rho_new_event_board"]:
    out = df_all[col].notna() & (
        (df_all[col] < RHO_MIN) | (df_all[col] > RHO_MAX)
    )
    df_all.loc[out, col] = float("nan")

# ── 3-E-6b. 적설판식 최종 우선순위 combine ───────────────────────────────
#
#   rho_new_board_3h 우선, 결측 시 rho_new_event_board 대체
#   (일 기준 rho_new_board_day는 참고용으로 유지, combine에서 제외)
#
#   우선순위: rho_new_board_3h → rho_new_event_board → (STEP 4에서 rho_exist)

df_all["rho_new_board"] = (
    df_all["rho_new_board_3h"].combine_first(df_all["rho_new_event_board"])
)

# ── 3-E-7. 이벤트 통계 출력 ──────────────────────────────────────────────
print(f"\n  이벤트 트리거 및 종료 기준")
print(f"  레이저식 (97개소): hs_chg_3h > 0  /  종료 기준 {GAP_HOURS_LASER}시간 연속 비활성")
print(f"  적설판식 (24개소): HN_3h    > 0  /  종료 기준 {GAP_HOURS_BOARD}시간 연속 비활성"
      f" (3h 관측간격 × 3회)")

# 레이저 이벤트 요약
n_laser_ev = (
    df_all[df_all["event_id_laser"] > 0]
    .groupby("STN")["event_id_laser"].nunique()
)
print(f"\n── 레이저 이벤트 요약 (97개소) ─────────────────────────")
print(f"  이벤트 발생 지점 수  : {(n_laser_ev > 0).sum()}개")
print(f"  지점당 최대 이벤트 수: {n_laser_ev.max()}개")
print(f"  지점당 평균 이벤트 수: {n_laser_ev.mean():.1f}개")

# 적설판 이벤트 요약
n_board_ev = (
    df_all[df_all["event_id_board"] > 0]
    .groupby("STN")["event_id_board"].nunique()
)
print(f"\n── 적설판 이벤트 요약 (24개소) ─────────────────────────")
if len(n_board_ev) > 0:
    print(f"  이벤트 발생 지점 수  : {(n_board_ev > 0).sum()}개")
    print(f"  지점당 최대 이벤트 수: {n_board_ev.max()}개")
    print(f"  지점당 평균 이벤트 수: {n_board_ev.mean():.1f}개")
else:
    print("  (이벤트 없음)")

print(f"\n── 이벤트 기반 신적설밀도 요약 ─────────────────────────")
rho_summary(df_all, "rho_new_event_laser",
            "rho_new_event_laser [레이저식] SWE_event_laser/HS_laser_event_cum")
rho_summary(df_all, "rho_new_event_board",
            "rho_new_event_board [적설판식] SWE_event_board/HN_3h_event_cum")

print(f"\n── 기준별 신적설밀도 유효값 비교 ───────────────────────")
print(f"  {'구분':<50} {'3시간':>6}  {'일 기준':>7}  {'이벤트':>7}")
print(f"  {'-'*72}")
n_l3h = df_all["rho_new_laser_3h"].notna().sum()
n_lev = df_all["rho_new_event_laser"].notna().sum()
n_b3h = df_all["rho_new_board_3h"].notna().sum()
n_bdy = df_all["rho_new_board_day"].notna().sum()
n_bev = df_all["rho_new_event_board"].notna().sum()
print(f"  {'레이저식 (97개소): rho_new_laser_3h / event_laser':<50}"
      f" {n_l3h:>6}  {'N/A':>7}  {n_lev:>7}")
print(f"  {'적설판식 (24개소): rho_new_board_3h / _day(참고) / _event':<50}"
      f" {n_b3h:>6}  {n_bdy:>7}  {n_bev:>7}")

print(f"\n── 적설판식 rho_new_board 최종 우선순위 현황 ───────────")
n_bd_3h  = df_all["rho_new_board_3h"].notna().sum()
n_bd_ev  = (
    df_all["rho_new_board_3h"].isna() & df_all["rho_new_event_board"].notna()
).sum()
n_bd_nan = df_all["rho_new_board"].isna().sum()
print(f"  rho_new_board_3h    적용 (3시간판, 우선)     : {n_bd_3h:>5}행")
print(f"  rho_new_event_board 적용 (이벤트 누적, 대체) : {n_bd_ev:>5}행")
print(f"  NaN (rho_exist 대체 예정 — STEP 4)           : {n_bd_nan:>5}행")
rho_summary(df_all, "rho_new_board",
            "rho_new_board [최종] 3h우선·이벤트대체")

print("\n  STEP 3-E 완료!")


# =============================================================================
#  STEP 4. 현 적설하중(L_current) 산출 — 3시간 간격
#
#  ■ 공통 공식: L_current [kN/m²] = ρ × HS_tot × 9.81 × 10⁻⁶
#    단위 유도: [kg/m³] × [mm] × 10⁻³[m/mm] × 9.81[m/s²] × 10⁻³[kN/N] = kN/m²
#
#  ■ 1단계: 24개소 적설판식 (BOARD_STNS)
#    ρ 우선: rho_new_board  (적설판 신적설밀도: 3h판 우선 → 이벤트 누적 대체)
#    ρ 대체: rho_exist      (SWE_cum/HS_tot 기반, rho_new_board 결측 시)
#    → rho_exist만 사용 시 L_current_board = L_current_laser (수학적 항등)
#      rho_new_board 적용으로 적설판 관측에 기반한 독립적 하중 산출 ✅
#
#  ■ 2단계: 97개소 레이저식 (전체)
#    ρ 1순위: rho_new_laser_3h    (무게식강수량계 SWE_3h / hs_chg_3h)
#             단, hs_chg_3h 는 전체 깊이 변화량(간접) → 침강 시 밀도 과대 추정 가능
#    ρ 2순위: rho_new_event_laser (이벤트 누적 SWE / 누적 깊이 변화량)
#    ρ 3순위: rho_exist           (SWE_cum/HS_tot, 결측 시 최후 대체)
#
#  ■ 조건 (공통): HS_tot > 0 (눈이 실제로 쌓인 경우에만 산출)
#
#  ■ 출력 간격: 3시간 (00, 03, 06, 09, 12, 15, 18, 21시)
# =============================================================================

print("\n" + "=" * 60)
print("  STEP 4. 현 적설하중(L_current) 산출")
print("=" * 60)

G = 9.81   # 중력가속도 (m/s²)

laser_stns = set(df_all["STN"].unique())   # 전체 97개소

print(f"\n  적설판식(board) 대상: {len(BOARD_STNS)}개소 / 밀도: rho_new_board_3h → rho_new_event_board → rho_exist")
print(f"  레이저식(laser) 대상: {len(laser_stns)}개소 / 밀도: rho_new_laser_3h → rho_new_event_laser → rho_exist")

# ── 4-1. 밀도 우선순위 적용 ──────────────────────────────────────────────
#
#   board: rho_new_board 우선, 결측 시 rho_exist 대체
#   laser: rho_new_laser_3h 우선 → rho_new_event_laser → rho_exist 대체

df_all["rho_for_board"] = (
    df_all["rho_new_board"].combine_first(df_all["rho_exist"])
)
df_all["rho_for_laser"] = (
    df_all["rho_new_laser_3h"]           # 1순위: 무게식강수량계 SWE_3h / hs_chg_3h
    .combine_first(df_all["rho_new_event_laser"])   # 2순위: 이벤트 누적 기반
    .combine_first(df_all["rho_exist"])             # 3순위: 현재 적설 평균밀도
)

# ── 4-2. 현 적설하중 계산 ────────────────────────────────────────────────

# [1단계] 적설판식 현 적설하중 (24개소)
mask_board_load = (
    df_all["STN"].isin(BOARD_STNS)
    & df_all["rho_for_board"].notna()
    & df_all["HS_tot"].notna()
    & (df_all["HS_tot"] > 0)
)
df_all["L_current_board"] = float("nan")
df_all.loc[mask_board_load, "L_current_board"] = (
    df_all.loc[mask_board_load, "rho_for_board"]
    * df_all.loc[mask_board_load, "HS_tot"]
    * G * 1e-6
)

# [2단계] 레이저식 현 적설하중 (97개소)
mask_laser_load = (
    df_all["STN"].isin(laser_stns)
    & df_all["rho_for_laser"].notna()
    & df_all["HS_tot"].notna()
    & (df_all["HS_tot"] > 0)
)
df_all["L_current_laser"] = float("nan")
df_all.loc[mask_laser_load, "L_current_laser"] = (
    df_all.loc[mask_laser_load, "rho_for_laser"]
    * df_all.loc[mask_laser_load, "HS_tot"]
    * G * 1e-6
)

# ── 4-3. 3시간 간격 필터링 ────────────────────────────────────────────────
df_3h = df_all[df_all["TM"].dt.hour % 3 == 0].copy()

# ── 4-4. 결과 확인 출력 ──────────────────────────────────────────────────

def load_summary(df, col, label):
    n   = df[col].notna().sum()
    mn  = df[col].min()  if n > 0 else float("nan")
    avg = df[col].mean() if n > 0 else float("nan")
    mx  = df[col].max()  if n > 0 else float("nan")
    print(f"  {label:<55} 유효:{n:>5}행  "
          f"min={mn:5.3f}  mean={avg:5.3f}  max={mx:5.3f}  kN/m²")

# 밀도 우선순위 적용 현황
n_board_new  = df_all[df_all["STN"].isin(BOARD_STNS)]["rho_new_board"].notna().sum()
n_board_fb   = (
    df_all[df_all["STN"].isin(BOARD_STNS)]["rho_new_board"].isna()
    & df_all[df_all["STN"].isin(BOARD_STNS)]["rho_exist"].notna()
).sum()
n_laser_ev   = df_all["rho_new_event_laser"].notna().sum()
n_laser_fb   = (
    df_all["rho_new_event_laser"].isna() & df_all["rho_exist"].notna()
).sum()

print(f"\n── 밀도 우선순위 적용 현황 ──────────────────────────────────────")
print(f"  [board] rho_new_board  적용 (우선): {n_board_new:>5}행")
print(f"  [board] rho_exist      적용 (대체): {n_board_fb:>5}행")
print(f"  [laser] rho_new_event_laser 적용 (우선): {n_laser_ev:>5}행")
print(f"  [laser] rho_exist           적용 (대체): {n_laser_fb:>5}행")

print(f"\n── 현 적설하중 산출 결과 (3시간 간격) ──────────────────────────")
print("  " + "-" * 85)
load_summary(df_3h, "L_current_board",
             "[1단계] L_current_board  적설판식 (rho_new_board→rho_exist)")
load_summary(df_3h, "L_current_laser",
             "[2단계] L_current_laser  레이저식 (rho_new_laser_3h→rho_new_event_laser→rho_exist)")

print("\n── 최대 적설하중 지점 Top 5 ─────────────────────────────────────")
for label, col in [("[board 24개소]", "L_current_board"),
                   ("[laser 97개소]", "L_current_laser")]:
    top5 = (
        df_3h.groupby("STN")[col].max()
        .dropna().sort_values(ascending=False).head(5).reset_index()
    )
    top5.columns = ["STN", f"{col}_max(kN/m²)"]
    print(f"\n  {label}")
    print(top5.to_string(index=False) if len(top5) > 0 else "  (유효값 없음)")

print("\n── 3시간 간격 결과 미리보기 ─────────────────────────────────────")
cols_load = [
    "TM", "STN",
    "HS_tot", "rho_for_board", "rho_for_laser",
    "L_current_board", "L_current_laser",
    "event_id_laser", "rho_new_event_laser",
    "event_id_board",  "rho_new_board",
]
df_preview = df_3h[
    df_3h["L_current_board"].notna() | df_3h["L_current_laser"].notna()
][cols_load].head(10)
print(df_preview.to_string(index=False) if len(df_preview) > 0
      else "  (유효값 없음)")

print("\n  STEP 4 완료!")

# ── [진단] STN 108 (서울) 레이저식 산출 과정 상세 추적 ────────────────────────
_diag_stn = 108
_diag = df_3h[df_3h["STN"] == _diag_stn].copy()
_diag_cols = [
    "TM",
    "HS_tot",       # 전체 적설 깊이
    "hs_chg_3h",    # 레이저 3h 깊이 변화량
    "SWE_3h",       # 무게식 강수량계 3h 수량
    "SWE_cum",      # 누적 수량
    "rho_new_laser_3h",   # 1순위 밀도
    "rho_new_event_laser",# 2순위 밀도
    "rho_exist",          # 3순위 밀도
    "rho_for_laser",      # 최종 적용 밀도
    "L_current_laser",    # 현 적설하중
]
_diag_avail = [c for c in _diag_cols if c in _diag.columns]
_diag_valid = _diag[_diag["L_current_laser"].notna()][_diag_avail]

print(f"\n{'='*70}")
print(f"  [진단] STN {_diag_stn} (서울) 레이저식 L_current 산출 상세")
print(f"{'='*70}")
if len(_diag_valid) > 0:
    print(_diag_valid.to_string(index=False))
    print(f"\n  ▶ L_current_laser 최대값 : "
          f"{_diag_valid['L_current_laser'].max():.4f} kN/m²")
    idx_max = _diag_valid["L_current_laser"].idxmax()
    print(f"  ▶ 최대값 발생 시각       : "
          f"{_diag_valid.loc[idx_max, 'TM']}")
    print(f"  ▶ 해당 시각 HS_tot       : "
          f"{_diag_valid.loc[idx_max, 'HS_tot']:.1f} mm")
    print(f"  ▶ 해당 시각 rho_for_laser: "
          f"{_diag_valid.loc[idx_max, 'rho_for_laser']:.1f} kg/m³")
    if "rho_new_laser_3h" in _diag_valid.columns:
        print(f"  ▶ 해당 시각 rho_new_laser_3h  : "
              f"{_diag_valid.loc[idx_max, 'rho_new_laser_3h']:.1f} kg/m³")
    if "hs_chg_3h" in _diag_valid.columns:
        print(f"  ▶ 해당 시각 hs_chg_3h  : "
              f"{_diag_valid.loc[idx_max, 'hs_chg_3h']:.1f} mm")
    if "SWE_3h" in _diag_valid.columns:
        print(f"  ▶ 해당 시각 SWE_3h     : "
              f"{_diag_valid.loc[idx_max, 'SWE_3h']:.1f} mm")
else:
    print(f"  STN {_diag_stn} 유효 데이터 없음")
print(f"{'='*70}\n")
# ─────────────────────────────────────────────────────────────────────────────


# =============================================================================
#  STEP 5. 시각화 — 현 적설하중 시계열 및 공간 분포
#
#  ■ 그림 1. 시계열: Top 5 board / Top 5 laser 지점의 L_current (3h 간격)
#  ■ 그림 2. 공간 분포: 분석기간 최대 L_current 버블 맵
#             · cartopy (PlateCarree) + 시도 경계 shapefile (geopandas)
#             · station_inform.csv 에서 지점 좌표 로딩
# =============================================================================

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patheffects as pe
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
import numpy as np
import os
import warnings
warnings.filterwarnings("ignore")

# ── Basemap ↔ 최신 matplotlib 호환 패치 ──────────────────────────────────────
#   Basemap이 내부적으로 dashes=[0,0] (all-zero) 을 사용하는데
#   matplotlib 3.7+ 에서 ValueError 발생 → all-zero → None(solid) 으로 교체
import matplotlib.backend_bases as _mbb
from matplotlib.backend_bases import GraphicsContextBase as _GCB

# ── Basemap ↔ matplotlib 3.7+ 호환 패치 ──────────────────────────────────────
# 진짜 원본을 _mbb 모듈 객체에 보관 → %run 재실행·중복 패치에 무관하게
# 항상 진짜 원본만 호출하므로 무한재귀 원천 차단
if not hasattr(_mbb, "_snow_orig_set_dashes"):
    # 아직 패치 전 → 진짜 원본 저장
    _mbb._snow_orig_set_dashes = _GCB.set_dashes

def _patched_set_dashes(self, dash_offset, dash_list):
    """all-zero dash_list → None(solid) 으로 변환 후 진짜 원본 호출."""
    if dash_list is not None:
        import numpy as _np
        dl = _np.asarray(dash_list)
        if dl.size > 0 and not _np.any(dl > 0):
            dash_list = None
    _mbb._snow_orig_set_dashes(self, dash_offset, dash_list)

# 매 %run 마다 재등록해도 항상 진짜 원본(_mbb._snow_orig_set_dashes)을 호출
_GCB.set_dashes = _patched_set_dashes
# ─────────────────────────────────────────────────────────────────────────────

from mpl_toolkits.basemap import Basemap

# ── 한글 폰트 (Windows 맑은 고딕) ────────────────────────────────────────────
matplotlib.rc("font", family="Malgun Gothic")
matplotlib.rc("axes", unicode_minus=False)

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
FIG_DIR      = r"E:\SNOW\OUTPUT\figures"
SHAPEFILE    = r"E:\SNOW\API_DATA\BND_SIDO_PG\BND_SIDO_PG.shp"
STATIONS_CSV = r"E:\SNOW\API_DATA\station_inform.csv"

os.makedirs(FIG_DIR, exist_ok=True)

print("\n" + "=" * 60)
print("  STEP 5. 시각화")
print("=" * 60)

# ── 지점 정보 로딩 (station_inform.csv) ──────────────────────────────────────
st_info = pd.read_csv(STATIONS_CSV)
st_info["lat"] = pd.to_numeric(st_info["lat"], errors="coerce")
st_info["lon"] = pd.to_numeric(st_info["lon"], errors="coerce")
st_info = st_info.dropna(subset=["lat", "lon"]).copy()
# stn_id → STN 정수 키로 통일
st_info["STN"] = st_info["stn_id"].astype(int)

print(f"  지점 정보 로딩: {len(st_info)}개소")

# ── Top 5 지점 선정 ──────────────────────────────────────────────────────────
top5_board = (
    df_3h.groupby("STN")["L_current_board"].max()
    .dropna().sort_values(ascending=False).head(5).index.tolist()
)
top5_laser = (
    df_3h.groupby("STN")["L_current_laser"].max()
    .dropna().sort_values(ascending=False).head(5).index.tolist()
)
print(f"  [적설판 Top 5] STN: {top5_board}")
print(f"  [레이저  Top 5] STN: {top5_laser}")

# 색상 팔레트 (Top 5 공통)
COLORS = ["#d62728", "#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd"]

# ── 지도 범위 ─────────────────────────────────────────────────────────────────
LL_LON, UR_LON = 124.0, 132.0
LL_LAT, UR_LAT = 33.0,  39.001

# =============================================================================
#  그림 1. 시계열 — Top 5 지점 L_current (적설판 / 레이저 상·하 2패널)
#  ※ tight_layout 경고 방지: constrained_layout=True 사용
# =============================================================================

fig1, axes = plt.subplots(
    2, 1, figsize=(13, 10), sharex=True,
    gridspec_kw={"hspace": 0.10},
    constrained_layout=True       # ← tight_layout 대체
)

panel_cfg = [
    ("적설판식 관측 (board, 24개소) — Top 5 지점",
     "L_current_board", top5_board),
    ("레이저식 관측 (laser, 97개소) — Top 5 지점",
     "L_current_laser", top5_laser),
]

for ax, (title, col, top5) in zip(axes, panel_cfg):
    for i, stn in enumerate(top5):
        sub = df_3h[df_3h["STN"] == stn][["TM", col]].dropna()
        if len(sub) == 0:
            continue
        stn_name = st_info.loc[st_info["STN"] == stn, "name"].values
        stn_name = stn_name[0] if len(stn_name) > 0 else str(stn)
        ax.plot(
            sub["TM"], sub[col],
            color=COLORS[i], linewidth=1.8,
            marker="o", markersize=4,
            label=f"STN {stn}  {stn_name}"
        )
        idx_max = sub[col].idxmax()
        ax.annotate(
            f"{sub.loc[idx_max, col]:.3f} kN/m²",
            xy=(sub.loc[idx_max, "TM"], sub.loc[idx_max, col]),
            xytext=(10, -14), textcoords="offset points",
            fontsize=7, ha="left", va="top", color=COLORS[i],
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                      edgecolor=COLORS[i], linewidth=0.7, alpha=0.75),
            arrowprops=dict(arrowstyle="-", color=COLORS[i],
                            linewidth=0.6, alpha=0.7)
        )
    ax.set_title(title, fontsize=11, fontweight="bold", loc="left", pad=4)
    ax.set_ylabel("현 적설하중 (kN/m²)", fontsize=10)
    ax.legend(loc="lower right", fontsize=9, ncol=1,
              framealpha=0.85, edgecolor="lightgray")
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.set_ylim(bottom=0)
    ax.axhline(0, color="black", linewidth=0.5)

axes[1].xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m/%d\n%H시"))
axes[1].set_xlabel("시각 (KST)", fontsize=10)

period_str = (f"{start_dt.strftime('%Y년 %m월 %d일')} ~ "
              f"{end_dt.strftime('%Y년 %m월 %d일')}")
fig1.suptitle(
    f"현 적설하중 시계열   ·   분석 기간: {period_str}",
    fontsize=13, fontweight="bold"
)

fig1_path = os.path.join(FIG_DIR, "fig1_timeseries_top5.png")
fig1.savefig(fig1_path, dpi=150, bbox_inches="tight")
plt.show()
print(f"\n  [저장] {fig1_path}")

# =============================================================================
#  그림 2. 공간 분포 — 분석기간 최대 L_current 버블 맵
#          cartopy (PlateCarree) + 시도 경계 shapefile (geopandas)
# =============================================================================

# ── 최대 하중 집계 및 지점 좌표 결합 ──────────────────────────────────────────
def make_spatial_df(max_series):
    df_m = max_series.dropna().reset_index()
    df_m.columns = ["STN", "max_load"]
    df_m["STN"] = df_m["STN"].astype(int)
    return df_m.merge(st_info[["STN", "lat", "lon", "name"]], on="STN", how="inner")

sp_board = make_spatial_df(df_3h.groupby("STN")["L_current_board"].max())
sp_laser = make_spatial_df(df_3h.groupby("STN")["L_current_laser"].max())

# 두 패널 공통 컬러 스케일
vmax_global = max(
    sp_board["max_load"].max() if len(sp_board) > 0 else 0,
    sp_laser["max_load"].max() if len(sp_laser) > 0 else 0,
    0.01
)

# ── 시도 경계 shapefile 로딩 ─────────────────────────────────────────────────
gdf = gpd.read_file(SHAPEFILE)
if gdf.crs is None or gdf.crs.to_epsg() != 4326:
    gdf = gdf.to_crs(epsg=4326)

# ── 시도 경계 그리기 함수 (site_location_map.py 동일) ────────────────────────
def draw_exterior_lines(geom, m, ax, lw=0.7):
    def _plot_ring(ring):
        lon = np.asarray(ring.coords.xy[0])
        lat = np.asarray(ring.coords.xy[1])
        x, y = m(lon, lat)
        ax.plot(x, y, color="black", linewidth=lw, zorder=4)
    if isinstance(geom, Polygon):
        _plot_ring(geom.exterior)
    elif isinstance(geom, MultiPolygon):
        for p in geom.geoms:
            _plot_ring(p.exterior)

# ── 전체 지점 데이터프레임 ───────────────────────────────────────────────────
all_stns_df = st_info[st_info["STN"].isin(df_3h["STN"].unique())].copy()

norm     = Normalize(vmin=0, vmax=vmax_global)
cmap     = plt.cm.YlOrRd
LABEL_DX = 3000   # 지점명 오프셋 (Mercator 단위 m)
LABEL_DY = 3000

MAP_CFG = dict(
    llcrnrlon=LL_LON, urcrnrlon=UR_LON,
    llcrnrlat=LL_LAT, urcrnrlat=UR_LAT,
    resolution="h", projection="merc", lat_ts=36.0
)

# ── 그림 생성 ─────────────────────────────────────────────────────────────────
fig2, axes2 = plt.subplots(1, 2, figsize=(17, 9.5), dpi=150)

panel_sp = [
    (sp_board, "(a) 적설판식  board, 24개소", top5_board),
    (sp_laser, "(b) 레이저식  laser, 97개소", top5_laser),
]

for ax, (sp_df, title, top5_list) in zip(axes2, panel_sp):

    # ── Basemap 초기화 ────────────────────────────────────────────────────
    #   fillcontinents → 북한·중국·일본 등 주변국 포함 육지 전체 채색
    #   (site_location_map.py 동일 방식)
    m = Basemap(ax=ax, **MAP_CFG)
    m.drawmapboundary(fill_color="lightblue")
    m.fillcontinents(color="lightgray", lake_color="lightblue")
    m.drawcoastlines(linewidth=0.6, color="black")

    # ── 위경도 눈금 (격자선 숨김, 라벨만 표시) ───────────────────────────
    m.drawparallels(np.arange(34, 39, 2),
                    labels=[1, 0, 0, 0], fontsize=8, linewidth=0)
    m.drawmeridians(np.arange(126, 131, 2),
                    labels=[0, 0, 0, 1], fontsize=8, linewidth=0)
    ax.tick_params(direction="out")

    # ── 남한 시도 경계: 경계선만 그리기 (채색 없음) ──────────────────────
    #   fillcontinents 의 lightgray 를 그대로 유지 → 북한과 동일한 배경색
    for geom in gdf.geometry:
        if geom is None or geom.is_empty:
            continue
        draw_exterior_lines(geom, m, ax, lw=0.7)

    # ── 배경 지점 (하중 없는 지점 — 회색 원) ─────────────────────────────
    bg_df = all_stns_df[~all_stns_df["STN"].isin(sp_df["STN"].values)]
    if len(bg_df) > 0:
        bx, by = m(bg_df["lon"].values, bg_df["lat"].values)
        ax.scatter(bx, by, s=20, marker="o",
                   facecolor="lightgray", edgecolor="gray",
                   linewidths=0.4, alpha=0.8, zorder=5)
        for _, row in bg_df.iterrows():
            xx, yy = m(row["lon"], row["lat"])
            ax.text(xx + LABEL_DX, yy + LABEL_DY, str(row["name"]),
                    fontsize=5.5, color="gray", zorder=6,
                    path_effects=[pe.withStroke(linewidth=0.8,
                                                foreground="white")])

    # ── 하중 버블 (하중 있는 지점 — 컬러맵) ─────────────────────────────
    sc = None
    if len(sp_df) > 0:
        bx2, by2 = m(sp_df["lon"].values, sp_df["lat"].values)
        sizes = np.clip(sp_df["max_load"] / vmax_global * 500 + 30, 30, 600)
        sc = ax.scatter(
            bx2, by2,
            c=sp_df["max_load"], cmap=cmap, norm=norm,
            s=sizes, alpha=0.88,
            edgecolors="dimgray", linewidths=0.6, zorder=7
        )
        for _, row in sp_df.iterrows():
            xx, yy = m(row["lon"], row["lat"])
            ax.text(xx + LABEL_DX, yy + LABEL_DY, str(row["name"]),
                    fontsize=5.5, zorder=8,
                    path_effects=[pe.withStroke(linewidth=0.9,
                                                foreground="white")])

    # ── Top 5 강조 테두리 + 라벨 ─────────────────────────────────────────
    # ── Top 5 라벨: 5방향 분산 오프셋 + 연결선으로 마커↔라벨 명확 대응 ──
    _lbl_off = [
        (-90000,  65000),   # 1위 — 좌상
        ( 90000,  55000),   # 2위 — 우상
        ( 85000, -65000),   # 3위 — 우하
        (-85000, -65000),   # 4위 — 좌하
        (    0,  90000),    # 5위 — 정상
    ]
    for i, stn in enumerate(top5_list):
        row = sp_df[sp_df["STN"] == stn]
        if len(row) == 0:
            continue
        val    = row["max_load"].values[0]
        name   = row["name"].values[0]
        xx, yy = m(row["lon"].values[0], row["lat"].values[0])
        ax.scatter(xx, yy,
                   s=np.clip(val / vmax_global * 500 + 30, 30, 600),
                   c=[val], cmap=cmap, norm=norm,
                   edgecolors=COLORS[i], linewidths=2.5, zorder=9)
        dx, dy = _lbl_off[i]
        ax.annotate(
            f"{name}  ({val:.3f} kN/m²)",
            xy=(xx, yy),                          # 마커 위치
            xytext=(xx + dx, yy + dy),            # 라벨 위치
            fontsize=7.5, fontweight="bold", color="#111111",
            ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                      edgecolor=COLORS[i], linewidth=1.4, alpha=0.75),
            arrowprops=dict(arrowstyle="-",        # 화살촉 없는 단순 연결선
                            color=COLORS[i], lw=1.2),
            zorder=11
        )

    # ── 컬러바 ────────────────────────────────────────────────────────────
    if sc is not None:
        cbar = fig2.colorbar(sc, ax=ax, shrink=0.68, pad=0.04)
        cbar.set_label("최대 현 적설하중 (kN/m²)", fontsize=9)
        cbar.ax.tick_params(labelsize=8)

    ax.set_title(title, fontsize=11, fontweight="bold", pad=8)

period_str = (f"{start_dt.strftime('%Y년 %m월 %d일')} ~ "
              f"{end_dt.strftime('%Y년 %m월 %d일')}")
fig2.suptitle(
    f"최대 현 적설하중 공간 분포   ·   분석 기간: {period_str}",
    fontsize=13, fontweight="bold"
)
fig2.subplots_adjust(left=0.04, right=0.96, top=0.91,
                     bottom=0.04, wspace=0.14)

fig2_path = os.path.join(FIG_DIR, "fig2_spatial_max_load.png")
fig2.savefig(fig2_path, dpi=150, bbox_inches="tight")
plt.show()
print(f"  [저장] {fig2_path}")

print(f"\n  저장 위치: {FIG_DIR}")
print("\n  STEP 5 완료!")
