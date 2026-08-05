
import json
import os
import unicodedata
import re
from datetime import datetime, timedelta, date
import time
import io
import zipfile

import subprocess
import sys

def ensure_library_installed(library):
    try:
        from tvDatafeed import TvDatafeed, Interval
    except ImportError:
        print("errode import", library)
        texto = 'pip install {} -t /tmp/ --no-cache-dir'.format(library)
        texto = 'pip install --upgrade --no-cache-dir git+https://github.com/rongardF/tvdatafeed.git'
        subprocess.call(texto.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sys.path.insert(1, '/tmp/')
        subprocess.check_call([sys.executable, "-m", "pip", "install", library])


for lib in ["tradingview-datafeed", "requests", "pandas"]:
    print('inicinado imports')
    ensure_library_installed(lib)
    print('fim imports')


import pandas as pd
import requests
import warnings
import numpy as np
warnings.filterwarnings('ignore')
import ssl
from tvDatafeed import TvDatafeed, Interval

ssl._create_default_context = ssl._create_unverified_context


bot_token = os.getenv("BOT_TOKEN")
chat_id = os.getenv("CHAT_ID")
fred_api_key = os.getenv("FRED_API_KEY")

bot_token = str(bot_token)
chat_id = str(chat_id)
fred_api_key = str(fred_api_key)


def aviso_via_telegram(msg_tel):
    mensagem = "Arcanine diz - " + msg_tel
    mensagem = msg_tel

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensagem
    }

    response = requests.post(url, json=payload)


def fetch_fred_rates():
    """
    Fetches historical values of the Federal Funds Rate (FEDFUNDS) and
    10-Year Treasury Rate (GS10) from the FRED API and returns a Pandas DataFrame.
    """
    base_url = "https://api.stlouisfed.org/fred/series/observations"
    series_ids = {"FEDFUNDS": "Federal Funds Rate", "GS10": "10-Year Treasury Rate"}
    today = datetime.today().strftime("%Y-%m-%d")

    data_frames = []

    for series_id, name in series_ids.items():
        params = {
            "series_id": series_id,
            "api_key": fred_api_key,
            "file_type": "json",
            "observation_start": "1950-01-01",  # Adjust as needed
            "observation_end": today
        }

        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            json_data = response.json()
            observations = json_data.get("observations", [])

            df = pd.DataFrame(observations)
            df["date"] = pd.to_datetime(df["date"])
            df[name] = pd.to_numeric(df["value"], errors='coerce')
            df = df[["date", name]]

            data_frames.append(df)
        else:
            print(f"Failed to fetch data for {series_id}: {response.status_code}")

    # Merge dataframes on date
    if data_frames:
        final_df = data_frames[0]
        for df in data_frames[1:]:
            final_df = final_df.merge(df, on="date", how="outer")
        final_df = final_df.sort_values("date").reset_index(drop=True)
        print('renomeando colunas fred')
        final_df.rename(columns={'10-Year Treasury Rate': 'rate_10y'}, inplace=True)
        final_df.rename(columns={'Federal Funds Rate': 'fed_rate'}, inplace=True)
        final_df.rename(columns={'date': 'data'}, inplace=True)
        # final_df['data'] = pd.to_datetime(final_df['data'], format="%d/%m/%Y")
        final_df['data'] = pd.to_datetime(final_df['data'], format="%Y-%m-%d")

        return final_df.sort_values("data").reset_index(drop=True)
    else:
        return pd.DataFrame()

def get_hist_completo_tv():

    tv = TvDatafeed()

    selic = tv.get_hist(symbol='BRINTR', exchange='ECONOMICS', interval=Interval.in_daily, n_bars=8000)

    di_fut = tv.get_hist(symbol='DI11!', exchange='BMFBOVESPA', interval=Interval.in_daily, n_bars=8000)

    rate_10y = tv.get_hist(symbol='US10Y', exchange='TVC', interval=Interval.in_daily, n_bars=8000)

    dolar = tv.get_hist(symbol='USDBRL', exchange='ActivTrades', interval=Interval.in_daily, n_bars=8000)

    df_final = pd.concat([selic, di_fut])
    df_final = pd.concat([df_final, rate_10y])
    df_final = pd.concat([df_final, dolar])

    df_final.reset_index(inplace=True)
    df_final.rename(columns={'datetime': 'Date'}, inplace=True)
    df_final['Date'] = pd.to_datetime(df_final['Date'])

    # Remover a hora da coluna 'Date' (ficando apenas com a data)
    df_final['Date'] = df_final['Date'].dt.date
    df_final = df_final.pivot(index='Date', columns='symbol', values='close')
    df_final.reset_index(inplace=True)
    df_final.rename(columns={'Date': 'data'}, inplace=True)

    df_final["data"] = pd.to_datetime(df_final["data"])
    print(df_final.head())
    print(df_final.tail())

    df_final['taxa_selic'] = df_final['ECONOMICS:BRINTR']
    df_final['juros_longos'] = df_final['BMFBOVESPA:DI11!']
    df_final['dolar'] = df_final['ActivTrades:USDBRL']
    # df_final['rate_10y'] = df_final['TVC:US10Y']

    return df_final

def arcanine_colab(d0, df_tds):
    # a dif das taxas indicara o que o mercado pensa vs. o que o governo tenta fazer ou o pessimismo/otimismo do merc com o governo/situacao
    # as difs de taxa deveriam indicar a direcao do cambio
    # aqui seriam representadas inversoes da curva de juros
    # em cenarios otimistas as dif seriam positivas
    # calc dif no d0
    df_tds_sem_filtro = df_tds
    try:
        df_tds = df_tds[df_tds['data'] <= d0]

        df_temp = df_tds[df_tds['data'] == d0]
        dolar_d0 = round(df_temp['dolar'].iloc[0], 2)
        taxa_selic = df_temp['taxa_selic'].iloc[0]
        fed_rate = df_temp['fed_rate'].iloc[0]
        juros_longos = df_temp['juros_longos'].iloc[0]
        rate_10y = df_temp['rate_10y'].iloc[0]
        dif_taxas_br = taxa_selic - juros_longos
        dif_taxas_us = fed_rate - rate_10y

        # vulgo que mercado esta mais otimista dif positiva br esta mais otimista
        dif_d0 = dif_taxas_br - dif_taxas_us

        # calculando medias ate d0
        # problema de comecar o backtest junto com a media... talvbez mudar comeco ou conseguir mais dados...
        # para simplificar comecar usando media simples de cada indice
        ######  talvez usar     dif_media_ate_d0 = media_dif_taxas_br_ate_d0 - media_dif_taxas_us_ate_d0

        df_temp = df_tds[df_tds['data'] <= d0]
        df_temp = df_temp[df_temp['data'] >= d0 - timedelta(days=2 * 365)]
        taxa_selic_media = df_temp['taxa_selic'].mean()
        fed_rate_media = df_temp['fed_rate'].mean()
        juros_longos_media = df_temp['juros_longos'].mean()
        rate_10y_media = df_temp['rate_10y'].mean()
        dif_taxas_br_media = taxa_selic_media - juros_longos_media
        dif_taxas_us_media = fed_rate_media - rate_10y_media
        dif_media_ate_d0 = dif_taxas_br_media - dif_taxas_us_media

        # calc o indicador
        indicador_arcanine_d0 = dif_d0 - dif_media_ate_d0
        # caso de nao ter indicador par ao dia por falta de dados
        if indicador_arcanine_d0 != indicador_arcanine_d0:
            print('sem indicador para o dia')

            return d0, 0, 0, 0, 0, 0

        vender = 'nada'
        comprar = 'nada'

        if indicador_arcanine_d0 > 0:
            vender = 'us'
        if indicador_arcanine_d0 < 0:
            vender = 'br'

        if indicador_arcanine_d0 > 0:
            comprar = 'br'
        if indicador_arcanine_d0 < 0:
            comprar = 'us'

        return d0, comprar, vender, indicador_arcanine_d0, dif_media_ate_d0, dolar_d0
    except:
        try:

            d0 = d0 + timedelta(days=1)
            df_tds = df_tds_sem_filtro[df_tds_sem_filtro['data'] <= d0]

            df_temp = df_tds[df_tds['data'] == d0]
            dolar_d0 = round(df_temp['dolar'].iloc[0], 2)
            taxa_selic = df_temp['taxa_selic'].iloc[0]
            fed_rate = df_temp['fed_rate'].iloc[0]
            juros_longos = df_temp['juros_longos'].iloc[0]
            rate_10y = df_temp['rate_10y'].iloc[0]
            dif_taxas_br = taxa_selic - juros_longos
            dif_taxas_us = fed_rate - rate_10y

            # vulgo que mercado esta mais otimista dif positiva br esta mais otimista
            dif_d0 = dif_taxas_br - dif_taxas_us

            # calculando medias ate d0
            # problema de comecar o backtest junto com a media... talvbez mudar comeco ou conseguir mais dados...
            # para simplificar comecar usando media simples de cada indice
            ######  talvez usar     dif_media_ate_d0 = media_dif_taxas_br_ate_d0 - media_dif_taxas_us_ate_d0

            df_temp = df_tds[df_tds['data'] <= d0]
            df_temp = df_temp[df_temp['data'] >= d0 - timedelta(days=2 * 365)]
            taxa_selic_media = df_temp['taxa_selic'].mean()
            fed_rate_media = df_temp['fed_rate'].mean()
            juros_longos_media = df_temp['juros_longos'].mean()
            rate_10y_media = df_temp['rate_10y'].mean()
            dif_taxas_br_media = taxa_selic_media - juros_longos_media
            dif_taxas_us_media = fed_rate_media - rate_10y_media
            dif_media_ate_d0 = dif_taxas_br_media - dif_taxas_us_media

            # calc o indicador
            indicador_arcanine_d0 = dif_d0 - dif_media_ate_d0
            # caso de nao ter indicador par ao dia por falta de dados
            if indicador_arcanine_d0 != indicador_arcanine_d0:
                print('sem indicador para o dia')

                return d0, 0, 0, 0, 0, 0

            # para a logica de o # de venda no indicador ser maior q de compra sempre que o robo for vender algo ele estara comprando o outro lado logo n existe venda sem compra no mesmo dia...

            vender = 'nada'
            comprar = 'nada'

            if indicador_arcanine_d0 > 0:
                vender = 'us'
            if indicador_arcanine_d0 < 0:
                vender = 'br'

            if indicador_arcanine_d0 > 0:
                comprar = 'br'
            if indicador_arcanine_d0 < 0:
                comprar = 'us'

            return d0, comprar, vender, indicador_arcanine_d0, dif_media_ate_d0, dolar_d0
        except:

            try:

                d0 = d0 + timedelta(days=1)
                df_tds = df_tds_sem_filtro[df_tds_sem_filtro['data'] <= d0]

                df_temp = df_tds[df_tds['data'] == d0]
                dolar_d0 = round(df_temp['dolar'].iloc[0], 2)
                taxa_selic = df_temp['taxa_selic'].iloc[0]
                fed_rate = df_temp['fed_rate'].iloc[0]
                juros_longos = df_temp['juros_longos'].iloc[0]
                rate_10y = df_temp['rate_10y'].iloc[0]
                dif_taxas_br = taxa_selic - juros_longos
                dif_taxas_us = fed_rate - rate_10y

                # vulgo que mercado esta mais otimista dif positiva br esta mais otimista
                dif_d0 = dif_taxas_br - dif_taxas_us

                # calculando medias ate d0
                # problema de comecar o backtest junto com a media... talvbez mudar comeco ou conseguir mais dados...
                # para simplificar comecar usando media simples de cada indice
                ######  talvez usar     dif_media_ate_d0 = media_dif_taxas_br_ate_d0 - media_dif_taxas_us_ate_d0

                df_temp = df_tds[df_tds['data'] <= d0]
                df_temp = df_temp[df_temp['data'] >= d0 - timedelta(days=2 * 365)]
                taxa_selic_media = df_temp['taxa_selic'].mean()
                fed_rate_media = df_temp['fed_rate'].mean()
                juros_longos_media = df_temp['juros_longos'].mean()
                rate_10y_media = df_temp['rate_10y'].mean()
                dif_taxas_br_media = taxa_selic_media - juros_longos_media
                dif_taxas_us_media = fed_rate_media - rate_10y_media
                dif_media_ate_d0 = dif_taxas_br_media - dif_taxas_us_media

                # calc o indicador
                indicador_arcanine_d0 = dif_d0 - dif_media_ate_d0
                # caso de nao ter indicador par ao dia por falta de dados
                if indicador_arcanine_d0 != indicador_arcanine_d0:
                    print('sem indicador para o dia')

                    return d0, 0, 0, 0, 0, 0

                # para a logica de o # de venda no indicador ser maior q de compra sempre que o robo for vender algo ele estara comprando o outro lado logo n existe venda sem compra no mesmo dia...

                vender = 'nada'
                comprar = 'nada'

                if indicador_arcanine_d0 > 0:
                    vender = 'us'
                if indicador_arcanine_d0 < 0:
                    vender = 'br'

                if indicador_arcanine_d0 > 0:
                    comprar = 'br'
                if indicador_arcanine_d0 < 0:
                    comprar = 'us'

                return d0, comprar, vender, indicador_arcanine_d0, dif_media_ate_d0, dolar_d0
            except:
                return d0, 0, 0, 0, 0, 0

def get_dados():
    df_tdv = get_hist_completo_tv()

    df_tds = fetch_fred_rates()

    df_tds = df_tds.sort_values(by='data')

    print(df_tds.head())
    print(df_tds.tail())
    df_tds = pd.merge(df_tdv, df_tds, on="data", how="outer")
    df_tds = df_tds.sort_values(by='data').reset_index(drop=True)
    print('dps do merge')
    print(df_tds.head())
    print(df_tds.tail())

    # df_tds = ffill_limitado(df_tds)

    df_tds = df_tds.ffill()

    return df_tds

def print_saida(df_tds):
        d0 = datetime.today().replace(hour=00, minute=00, second=00, microsecond=00)
        d1 = d0 - timedelta(days=1)
        sem_ant = d0 - timedelta(days=7)
        mes_ant = d0 - timedelta(days=31)
        semestre_ant = d0 - timedelta(days=180)
        ano_ant = d0 - timedelta(days=365)
        ano2_ant = d0 - timedelta(days=365 * 2)
        ano5_ant = d0 - timedelta(days=365 * 5)
        ano10_ant = d0 - timedelta(days=365 * 10)
        ano15_ant = d0 - timedelta(days=365 * 15)
        ano19_ant = d0 - timedelta(days=365 * 19)

        df_tds = df_tds[df_tds['data'] <= d0]
        # saida = df_tds.to_excel('df_taxas_br_us.xlsx', index=False)

        data_inicio_backtest = datetime(2000, 1, 1)
        ############### juros longos com dados estranhos antes de 2006
        data_inicio_backtest = datetime(2006, 1, 1)
        # data_inicio_backtest = datetime(2006, 1, 1)
        # data_inicio_backtest = datetime(2010, 1, 1)
        # data_inicio_backtest = datetime(2015, 1, 1)
        # data_inicio_backtest = datetime(2020, 1, 1)

        df_tds = df_tds[df_tds['data'] >= data_inicio_backtest]

        data_19ano_ant, comprar_19ano_ant, vender_19ano_ant, indicador_arcanine_19ano_ant, dif_media_ate_19ano_ant, dolar_19ano_ant = arcanine_colab(ano19_ant, df_tds)

        data_15ano_ant, comprar_15ano_ant, vender_15ano_ant, indicador_arcanine_15ano_ant, dif_media_ate_15ano_ant, dolar_15ano_ant = arcanine_colab(ano15_ant, df_tds)

        data_10ano_ant, comprar_10ano_ant, vender_10ano_ant, indicador_arcanine_10ano_ant, dif_media_ate_10ano_ant, dolar_10ano_ant = arcanine_colab(ano10_ant, df_tds)

        data_5ano_ant, comprar_5ano_ant, vender_5ano_ant, indicador_arcanine_5ano_ant, dif_media_ate_5ano_ant, dolar_5ano_ant = arcanine_colab(ano5_ant, df_tds)

        data_2ano_ant, comprar_2ano_ant, vender_2ano_ant, indicador_arcanine_2ano_ant, dif_media_ate_2ano_ant, dolar_2ano_ant = arcanine_colab(ano2_ant, df_tds)

        data_ano_ant, comprar_ano_ant, vender_ano_ant, indicador_arcanine_ano_ant, dif_media_ate_ano_ant, dolar_ano_ant = arcanine_colab(ano_ant, df_tds)

        data_semestre_ant, comprar_semestre_ant, vender_semestre_ant, indicador_arcanine_semestre_ant, dif_media_ate_semestre_ant, dolar_semestre_ant = arcanine_colab(
            semestre_ant, df_tds)

        data_mes_ant, comprar_mes_ant, vender_mes_ant, indicador_arcanine_mes_ant, dif_media_ate_mes_ant, dolar_mes_ant = arcanine_colab(mes_ant, df_tds)

        data_sem_ant, comprar_sem_ant, vender_sem_ant, indicador_arcanine_sem_ant, dif_media_ate_sem_ant, dolar_sem_ant = arcanine_colab(sem_ant, df_tds)

        data_ant, comprar_ant, vender_ant, indicador_arcanine_d1, dif_media_ate_d1, dolar_d1 = arcanine_colab(d1, df_tds)

        data, comprar, vender, indicador_arcanine_d0, dif_media_ate_d0, dolar_d0 = arcanine_colab(d0, df_tds)
        # try:
        #     data, comprar, vender, indicador_arcanine_d0 = arcanine_colab(d0, df_tds)
        # except:
        #     df_tds = preencher_ultimo_yfinance(df_tds)
        #     data, comprar, vender, indicador_arcanine_d0 = arcanine_colab(d0, df_tds)

        print(' ', data_19ano_ant, ' comprar_19ano_ant    ', comprar_19ano_ant, ' dolar ', dolar_19ano_ant, ' vender_19ano_ant     ', vender_19ano_ant, ' indicador_arcanine_19ano_ant     ',
              indicador_arcanine_19ano_ant, ' dif_media_ate_19ano_ant  ',
              dif_media_ate_19ano_ant)
        print(' ', data_15ano_ant, ' comprar_15ano_ant    ', comprar_15ano_ant, ' dolar ', dolar_15ano_ant, ' vender_15ano_ant     ', vender_15ano_ant, ' indicador_arcanine_15ano_ant      ',
              indicador_arcanine_15ano_ant, ' dif_media_ate_15ano_ant  ',
              dif_media_ate_15ano_ant)
        print(' ', data_10ano_ant, ' comprar_10ano_ant    ', comprar_10ano_ant, ' dolar ', dolar_10ano_ant, ' vender_10ano_ant     ', vender_10ano_ant, ' indicador_arcanine_10ano_ant      ',
              indicador_arcanine_10ano_ant, ' dif_media_ate_10ano_ant ',
              dif_media_ate_10ano_ant)
        print(' ', data_5ano_ant, ' comprar_5ano_ant     ', comprar_5ano_ant, ' dolar ', dolar_5ano_ant, ' vender_5ano_ant      ', vender_5ano_ant, ' indicador_arcanine_5ano_ant      ',
              indicador_arcanine_5ano_ant, ' dif_media_ate_5ano_ant  ',
              dif_media_ate_5ano_ant)
        print(' ', data_2ano_ant, ' comprar_2ano_ant     ', comprar_2ano_ant, ' dolar ', dolar_2ano_ant, ' vender_2ano_ant      ', vender_2ano_ant, ' indicador_arcanine_2ano_ant      ',
              indicador_arcanine_2ano_ant, ' dif_media_ate_2ano_ant   ',
              dif_media_ate_2ano_ant)
        print(' ', data_ano_ant, ' comprar_ano_ant      ', comprar_ano_ant, ' dolar ', dolar_ano_ant, ' vender_ano_ant       ', vender_ano_ant, ' indicador_arcanine_ano_ant       ',
              indicador_arcanine_ano_ant, ' dif_media_ate_ano_ant    ',
              dif_media_ate_ano_ant)
        print(' ', data_semestre_ant, ' comprar_semestre_ant ', comprar_semestre_ant, ' dolar ', dolar_semestre_ant, ' vender_semestre_ant  ', vender_semestre_ant, ' indicador_arcanine_semestre_ant  ',
              indicador_arcanine_semestre_ant, ' dif_media_ate_semestre_ant ',
              dif_media_ate_semestre_ant)
        print(' ', data_mes_ant, ' comprar_mes_ant      ', comprar_mes_ant, ' dolar ', dolar_mes_ant, ' vender_mes_ant       ', vender_mes_ant, ' indicador_arcanine_mes_ant       ',
              indicador_arcanine_mes_ant, ' dif_media_ate_mes_ant     ',
              dif_media_ate_mes_ant)
        print(' ', data_sem_ant, ' comprar_sem_ant      ', comprar_sem_ant, ' dolar ', dolar_sem_ant, ' vender_sem_ant       ', vender_sem_ant, ' indicador_arcanine_sem_ant       ',
              indicador_arcanine_sem_ant, ' dif_media_ate_sem_ant    ',
              dif_media_ate_sem_ant)
        print(' ', data_ant, ' comprar_ant          ', comprar_ant, ' dolar ', dolar_d1, ' vender_ant           ', vender_ant, ' indicador_arcanine_d1            ',
              indicador_arcanine_d1, ' dif_media_ate_d1         ',
              dif_media_ate_d1)
        print(' ', data, ' comprar              ', comprar, ' dolar ', dolar_d0, ' vender               ', vender, ' indicador_arcanine_d0            ', indicador_arcanine_d0, ' dif_media_ate_d0         ',
              dif_media_ate_d0)

        def seta(valor):
            # return "↑" if float(valor) >= 0 else "↓"
            return "↑" if float(float(valor) - float(dif_media_ate_d0)) >= 0 else "↓"

        msg_tel = (
            f"({data_19ano_ant}) 📅 19 anos atrás:\n"
            f"  Comprar: {comprar_19ano_ant}  |  Dólar: {float(dolar_19ano_ant):.2f}  |  Vender: {vender_19ano_ant}\n"
            f"  Ind. Arc: {float(indicador_arcanine_19ano_ant):.3f}{seta(indicador_arcanine_19ano_ant)}  |  Dif. Média: {float(dif_media_ate_19ano_ant):.3f}\n\n"

            f"({data_15ano_ant}) 📅 15 anos atrás:\n"
            f"  Comprar: {comprar_15ano_ant}  |  Dólar: {float(dolar_15ano_ant):.2f}  |  Vender: {vender_15ano_ant}\n"
            f"  Ind. Arc: {float(indicador_arcanine_15ano_ant):.3f}{seta(indicador_arcanine_15ano_ant)}  |  Dif. Média: {float(dif_media_ate_15ano_ant):.3f}\n\n"

            f"({data_10ano_ant}) 📅 10 anos atrás:\n"
            f"  Comprar: {comprar_10ano_ant}  |  Dólar: {float(dolar_10ano_ant):.2f}  |  Vender: {vender_10ano_ant}\n"
            f"  Ind. Arc: {float(indicador_arcanine_10ano_ant):.3f}{seta(indicador_arcanine_10ano_ant)}  |  Dif. Média: {float(dif_media_ate_10ano_ant):.3f}\n\n"

            f"({data_5ano_ant}) 📅 5 anos atrás:\n"
            f"  Comprar: {comprar_5ano_ant}  |  Dólar: {float(dolar_5ano_ant):.2f}  |  Vender: {vender_5ano_ant}\n"
            f"  Ind. Arc: {float(indicador_arcanine_5ano_ant):.3f}{seta(indicador_arcanine_5ano_ant)}  |  Dif. Média: {float(dif_media_ate_5ano_ant):.3f}\n\n"

            f"({data_2ano_ant}) 📅 2 anos atrás:\n"
            f"  Comprar: {comprar_2ano_ant}  |  Dólar: {float(dolar_2ano_ant):.2f}  |  Vender: {vender_2ano_ant}\n"
            f"  Ind. Arc: {float(indicador_arcanine_2ano_ant):.3f}{seta(indicador_arcanine_2ano_ant)}  |  Dif. Média: {float(dif_media_ate_2ano_ant):.3f}\n\n"

            f"({data_ano_ant}) 📅 1 ano atrás:\n"
            f"  Comprar: {comprar_ano_ant}  |  Dólar: {float(dolar_ano_ant):.2f}  |  Vender: {vender_ano_ant}\n"
            f"  Ind. Arc: {float(indicador_arcanine_ano_ant):.3f}{seta(indicador_arcanine_ano_ant)}  |  Dif. Média: {float(dif_media_ate_ano_ant):.3f}\n\n"

            f"({data_semestre_ant}) 📅 Último semestre:\n"
            f"  Comprar: {comprar_semestre_ant}  |  Dólar: {float(dolar_semestre_ant):.2f}  |  Vender: {vender_semestre_ant}\n"
            f"  Ind. Arc: {float(indicador_arcanine_semestre_ant):.3f}{seta(indicador_arcanine_semestre_ant)}  |  Dif. Média: {float(dif_media_ate_semestre_ant):.3f}\n\n"

            f"({data_mes_ant}) 📅 Último mês:\n"
            f"  Comprar: {comprar_mes_ant}  |  Dólar: {float(dolar_mes_ant):.2f}  |  Vender: {vender_mes_ant}\n"
            f"  Ind. Arc: {float(indicador_arcanine_mes_ant):.3f}{seta(indicador_arcanine_mes_ant)}  |  Dif. Média: {float(dif_media_ate_mes_ant):.3f}\n\n"

            f"({data_sem_ant}) 📅 Última quinzena:\n"
            f"  Comprar: {comprar_sem_ant}  |  Dólar: {float(dolar_sem_ant):.2f}  |  Vender: {vender_sem_ant}\n"
            f"  Ind. Arc: {float(indicador_arcanine_sem_ant):.3f}{seta(indicador_arcanine_sem_ant)}  |  Dif. Média: {float(dif_media_ate_sem_ant):.3f}\n\n"

            f"({data_ant}) 📅 Ontem:\n"
            f"  Comprar: {comprar_ant}  |  Dólar: {float(dolar_d1):.2f}  |  Vender: {vender_ant}\n"
            f"  Ind. Arc: {float(indicador_arcanine_d1):.3f}{seta(indicador_arcanine_d1)}  |  Dif. Média: {float(dif_media_ate_d1):.3f}\n\n"

            f"({data}) 📅 Hoje:\n"
            f"  Comprar: {comprar}  |  Dólar: {float(dolar_d0):.2f}  |  Vender: {vender}\n"
            f"  Ind. Arc: {float(indicador_arcanine_d0):.3f}{seta(indicador_arcanine_d0)}  |  Dif. Média: {float(dif_media_ate_d0):.3f}"
        )

        return msg_tel


def ind_arca_hist():



    df_arcanine = pd.DataFrame()


    def criar_hist_arcanine(d0, df_tds):
        import plotly.graph_objects as go
        data_inicio_backtest = datetime(2006, 1, 1)
        df_tds = df_tds[df_tds['data'] >= data_inicio_backtest]

        df_tds = df_tds[df_tds['data'] <= d0]

        dx = data_inicio_backtest
        lista_de_datas = []
        while dx < d0:
            lista_de_datas.append(dx)
            dx = dx + timedelta(days=1)

        lista_de_datas.append(d0)

        lista_hist = []
        for dx in lista_de_datas:
            d0, comprar, vender, indicador_arcanine_d0, dif_media_ate_d0, dolar_d0 = arcanine_colab(dx, df_tds)
            print(d0, comprar, vender, indicador_arcanine_d0, dif_media_ate_d0, dolar_d0)
            dic = {'data': d0, 'comprar': comprar, 'vender': vender, 'indicador_arcanine_d0': indicador_arcanine_d0, 'dif_media_ate_d0': dif_media_ate_d0, 'dolar_d0': dolar_d0}
            lista_hist.append(dic)

        df_hist = pd.DataFrame(lista_hist)
        # Preencher apenas os zeros com o valor anterior (ffill)
        # df_hist['indicador_arcanine_pc'] = df_hist['indicador_arcanine_d0'].pct_change()
        df_hist['sinal_arca'] = np.sign(df_hist['indicador_arcanine_d0'])
        df_hist["dolar_d0"] = df_hist["dolar_d0"].mask(df_hist["dolar_d0"] == 0).ffill()
        df_hist['dolar_perc'] = df_hist['dolar_d0'].pct_change() * 100
        df_hist['dolar_perc_7d'] = df_hist['dolar_d0'].pct_change(periods=7)

        saida = df_hist.to_excel('df_hist.xlsx', index=False)

        # Criando a figura
        fig = go.Figure()

        # Linha da coluna1
        fig.add_trace(go.Scatter(
            x=df_hist['data'],
            y=df_hist['indicador_arcanine_d0'],
            mode='lines',  # Apenas linhas, sem marcadores
            name='ind arca'
        ))

        # Linha da coluna2
        fig.add_trace(go.Scatter(
            x=df_hist['data'],
            y=df_hist['dolar_d0'],
            mode='lines',
            name='dolar'
        ))
        # Linha da coluna2
        fig.add_trace(go.Scatter(
            x=df_hist['data'],
            y=df_hist['sinal_arca'],
            mode='lines',
            name='sinal_arca'
        ))

        # Personalização do layout
        fig.update_layout(
            title='Pos. compra BR - neg. compra EUA',
            xaxis_title='Data',
            yaxis_title='',
            hovermode='x unified',
            template='plotly_white'
        )

        # Mostrar o gráfico
        fig.show()
        return df_hist

    try:
        df_tds = pd.read_excel('db_tds.xlsx')
        print('usando planilha existente...')
    except:
        print('excel n encontrado baixando dados...')
        df_tds = get_dados()
        # print('salvando excel...')
        # saida = df_tds.to_excel('db_tds.xlsx', index=False)

    d0 = datetime.today().replace(hour=00, minute=00, second=00, microsecond=00)

    msg_tel = print_saida(df_tds)

    aviso_via_telegram(msg_tel)

    pare = 1
print('iniciando')
ind_arca_hist()
print('fim')
