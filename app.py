# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

st.set_page_config(page_title="KOSPI Momentum", page_icon="📈", layout="wide")

st.title("📈 코스피 모멘텀 전략 자동 탐색")
st.write("버튼을 누르면 실시간으로 데이터를 수집하여 이번 달 매수 종목을 계산합니다.")
st.caption("전략: 코스피 시총 상위 20개 | 평균 모멘텀 1위 단일 매수 | TIP ETF 필터 | 매월 말일 리밸런싱")

# =========================================================
# 모멘텀 계산 함수
# =========================================================
def avg_momentum(series):
    s = series.dropna()
    if len(s) < 13:
        return np.nan, np.nan, np.nan, np.nan, np.nan
    p = s.iloc[-1]
    r1  = p / s.iloc[-2]  - 1
    r3  = p / s.iloc[-4]  - 1
    r6  = p / s.iloc[-7]  - 1
    r12 = p / s.iloc[-13] - 1
    avg = (r1 + r3 + r6 + r12) / 4
    return avg, r1, r3, r6, r12


# =========================================================
# 코스피 시총 상위 N개 수집 (네이버 금융 크롤링)
# 실패시 하드코딩 폴백 사용
# =========================================================
@st.cache_data(ttl=86400)
def get_kospi_top_n(n=20):
    FALLBACK = {
        '005930.KS': '삼성전자',
        '000660.KS': 'SK하이닉스',
        '005380.KS': '현대차',
        '000270.KS': '기아',
        '005490.KS': 'POSCO홀딩스',
        '035420.KS': 'NAVER',
        '051910.KS': 'LG화학',
        '006400.KS': '삼성SDI',
        '035720.KS': '카카오',
        '003550.KS': 'LG',
        '055550.KS': '신한지주',
        '105560.KS': 'KB금융',
        '028260.KS': '삼성물산',
        '012330.KS': '현대모비스',
        '066570.KS': 'LG전자',
        '003490.KS': '대한항공',
        '017670.KS': 'SK텔레콤',
        '030200.KS': 'KT',
        '032830.KS': '삼성생명',
        '086790.KS': '하나금융지주',
    }

    try:
        from bs4 import BeautifulSoup
        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            )
        }
        url = 'https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1'
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = 'euc-kr'
        soup = BeautifulSoup(resp.text, 'html.parser')

        codes_names = {}
        for a_tag in soup.select('td.ctg a[href*="code="]'):
            href = a_tag.get('href', '')
            name = a_tag.text.strip()
            if 'code=' in href:
                code = href.split('code=')[-1][:6]
                yf_tk = code + '.KS'
                codes_names[yf_tk] = name
                if len(codes_names) >= n:
                    break

        if len(codes_names) >= 5:
            return list(codes_names.keys())[:n], codes_names

    except Exception:
        pass

    return list(FALLBACK.keys())[:n], FALLBACK


# =========================================================
# 메인 실행
# =========================================================
if st.button("🚀 전략 실행 및 결과 보기", type="primary"):

    TOP_N = 20
    TIP_TICKER = 'TIP'

    with st.status("🔄 데이터 수집 및 계산 중...") as status:

        # Step 1: 코스피 종목 수집
        st.write("📋 코스피 시총 상위 종목 수집 중...")
        try:
            top20_tickers, name_map = get_kospi_top_n(TOP_N)
            name_list = [name_map.get(tk, tk) for tk in top20_tickers]
            st.write(f"✅ {len(top20_tickers)}개 종목 확인: {' · '.join(name_list)}")
        except Exception as e:
            st.error(f"종목 목록 수집 실패: {e}")
            st.stop()

        # Step 2: 주가 데이터 수집
        st.write("📡 주가 데이터 수집 중 (14개월)...")
        try:
            end_date   = datetime.today()
            start_date = end_date - timedelta(days=430)

            raw = yf.download(
                top20_tickers + [TIP_TICKER],
                start=start_date.strftime('%Y-%m-%d'),
                end=end_date.strftime('%Y-%m-%d'),
                auto_adjust=True,
                progress=False
            )

            if isinstance(raw.columns, pd.MultiIndex):
                prices = raw['Close']
            else:
                prices = raw[['Close']]

            monthly = prices.resample('ME').last()

            available = [
                tk for tk in top20_tickers
                if tk in monthly.columns and monthly[tk].notna().sum() >= 5
            ]
            missing = [tk for tk in top20_tickers if tk not in available]
            st.write(
                f"✅ {len(monthly)}개월치 수집 완료 "
                f"({len(available)}개 정상 / {len(missing)}개 누락)"
            )
            if missing:
                st.caption("누락: " + ", ".join([name_map.get(tk, tk) for tk in missing]))

        except Exception as e:
            st.error(f"주가 데이터 수집 실패: {e}")
            st.stop()

        # Step 3: TIP 필터
        st.write("🔍 TIP ETF 필터 확인 중...")
        try:
            if TIP_TICKER not in monthly.columns:
                st.error("TIP ETF 데이터를 가져오지 못했습니다.")
                st.stop()
            tip_avg, tip_r1, tip_r3, tip_r6, tip_r12 = avg_momentum(monthly[TIP_TICKER])
            tip_pass = (not np.isnan(tip_avg)) and (tip_avg > 0)
        except Exception as e:
            st.error(f"TIP 필터 계산 실패: {e}")
            st.stop()

        # Step 4: 모멘텀 계산
        st.write("🧮 종목별 모멘텀 계산 중...")
        momentum_rows = []
        for tk in available:
            if tk not in monthly.columns:
                continue
            m_avg, r1, r3, r6, r12 = avg_momentum(monthly[tk])
            if any(np.isnan(v) for v in [m_avg, r1, r3, r6, r12]):
                continue
            momentum_rows.append({
                '종목코드':      tk.replace('.KS', ''),
                '종목명':        name_map.get(tk, tk),
                '1M(%)':        round(r1    * 100, 2),
                '3M(%)':        round(r3    * 100, 2),
                '6M(%)':        round(r6    * 100, 2),
                '12M(%)':       round(r12   * 100, 2),
                '평균모멘텀(%)': round(m_avg * 100, 2),
            })

        df_rank = (
            pd.DataFrame(momentum_rows)
            .sort_values('평균모멘텀(%)', ascending=False)
            .reset_index(drop=True)
        )
        df_rank.index += 1
        status.update(label="✅ 계산 완료!", state="complete")

    # =========================================================
    # 결과 출력
    # =========================================================
    st.divider()
    st.subheader("📊 전략 결과 요약")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "TIP 모멘텀 (인플레 필터)",
        f"{tip_avg*100:.2f}%" if not np.isnan(tip_avg) else "N/A",
        "PASS ✅" if tip_pass else "BLOCK 🚫"
    )
    c2.metric("분석 종목 수", f"{len(df_rank)}개")
    c3.metric("기준일", datetime.today().strftime('%Y-%m-%d'))
    next_rebal = (
        datetime.today().replace(day=1) + timedelta(days=32)
    ).replace(day=1)
    c4.metric("다음 리밸런싱", next_rebal.strftime('%Y-%m 말일'))

    st.divider()

    # 매수/현금 신호
    if not tip_pass:
        st.error(
            f"🚫 **TIP 필터 차단** (TIP 평균 모멘텀: {tip_avg*100:.2f}%)  \n"
            "→ **이번 달은 전량 현금 보유하세요!**"
        )
    elif len(df_rank) == 0:
        st.warning("⚠️ 모멘텀을 계산할 수 있는 종목이 없습니다.")
    else:
        best = df_rank.iloc[0]
        st.success(f"✅ TIP 필터 통과! (TIP 평균 모멘텀: {tip_avg*100:.2f}%)")
        st.info(
            f"🎯 **이번 달 추천 매수 종목: {best['종목명']} ({best['종목코드']})**  \n"
            f"평균 모멘텀: **{best['평균모멘텀(%)']:+.2f}%** "
            f"| 1M: {best['1M(%)']:+.2f}% "
            f"| 3M: {best['3M(%)']:+.2f}% "
            f"| 6M: {best['6M(%)']:+.2f}% "
            f"| 12M: {best['12M(%)']:+.2f}%"
        )

    # TIP 상세
    with st.expander("🔍 TIP ETF 상세 보기"):
        if not np.isnan(tip_avg):
            t1, t2, t3, t4, t5 = st.columns(5)
            t1.metric("1개월",  f"{tip_r1*100:+.3f}%")
            t2.metric("3개월",  f"{tip_r3*100:+.3f}%")
            t3.metric("6개월",  f"{tip_r6*100:+.3f}%")
            t4.metric("12개월", f"{tip_r12*100:+.3f}%")
            t5.metric("평균",   f"{tip_avg*100:+.3f}%",
                      "매수 가능 ✅" if tip_pass else "현금 보유 🚫")
        st.caption(
            "TIP = iShares TIPS Bond ETF. "
            "인플레이션 기대를 반영하며 양수일 때 위험자산 매수 환경입니다."
        )

    # 순위표
    st.divider()
    st.subheader("🏆 코스피 시총 상위 종목 모멘텀 순위")

    if len(df_rank) > 0:
        def color_momentum(val):
            if isinstance(val, (int, float)) and not np.isnan(val):
                color = '#39d98a' if val >= 0 else '#ff4757'
                return f'color: {color}; font-weight: bold'
            return ''

        try:
            styled = df_rank.style.map(
                color_momentum,
                subset=['1M(%)', '3M(%)', '6M(%)', '12M(%)', '평균모멘텀(%)']
            )
        except AttributeError:
            styled = df_rank.style.applymap(
                color_momentum,
                subset=['1M(%)', '3M(%)', '6M(%)', '12M(%)', '평균모멘텀(%)']
            )

        st.dataframe(styled, use_container_width=True, height=500)

        st.subheader("📊 평균 모멘텀 순위 차트")
        chart_data = (
            df_rank.set_index('종목명')[['평균모멘텀(%)']]
            .sort_values('평균모멘텀(%)')
        )
        st.bar_chart(chart_data, color='#00d4ff')
