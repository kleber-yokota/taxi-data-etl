"""
Fuzz test para extract.parser.generate_parquet_urls

Baseado na implementação real do parser.py:
- VALID_DATASETS = {"yellow", "green", "fhv", "hvfhv"}
- _check_dataset: TypeError se não str, ValueError se não no set
- _check_year: TypeError se não int ou se bool
- _check_month: TypeError se não int ou se bool, ValueError se fora de 1-12
- _validate_*: TypeError se não iterável (ex: years=None)
- datasets=None usa todos os 4 válidos
"""

import sys

import atheris

with atheris.instrument_imports():
    from extract.parser import BASE_S3_URL, VALID_DATASETS, generate_parquet_urls

VALID_DATASETS_LIST = sorted(VALID_DATASETS)

# Exceções esperadas — o fuzzer as ignora e continua
EXPECTED_EXCEPTIONS = (TypeError, ValueError)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _assert_valid_result(result, datasets, years, months):
    """Verifica invariantes quando a função retorna com sucesso."""

    assert isinstance(result, list), f"Retorno deve ser list, recebeu {type(result)}"

    for url in result:
        assert isinstance(url, str), f"Cada URL deve ser str: {url!r}"
        assert url.startswith(BASE_S3_URL), f"URL com prefixo errado: {url}"
        assert url.endswith(".parquet"), f"URL deve terminar com .parquet: {url}"

    # Contagem: datasets * years * months (sem duplicatas, pois _validate usa set)
    u_datasets = len(set(datasets))
    u_years = len(set(years))
    u_months = len(set(months))
    expected = u_datasets * u_years * u_months

    assert len(result) == expected, (
        f"Contagem errada: esperado {expected} ({u_datasets}d x {u_years}y x {u_months}m), "
        f"recebeu {len(result)}"
    )

    # Ordem cronologica: year asc, depois month asc (por dataset)
    for dataset in set(datasets):
        dataset_urls = [u for u in result if f"/{dataset}_tripdata_" in u]
        dates = []
        for url in dataset_urls:
            date_part = url.split("_tripdata_")[-1].replace(".parquet", "")
            y, m = date_part.split("-")
            dates.append((int(y), int(m)))
        assert dates == sorted(dates), (
            f"Dataset '{dataset}' fora de ordem cronologica: {dates}"
        )


# ── Estrategia 1: seeds reais com valores validos ─────────────────────────────


def fuzz_valid_seeds(data):
    """
    Usa os bytes do fuzzer para SELECIONAR dentro de valores conhecidos.
    Garante que o fuzzer explore os caminhos felizes da funcao.
    """
    fdp = atheris.FuzzedDataProvider(data)

    try:
        num_datasets = fdp.ConsumeIntInRange(1, 4)
        datasets = [
            fdp.PickValueInList(VALID_DATASETS_LIST) for _ in range(num_datasets)
        ]

        num_years = fdp.ConsumeIntInRange(1, 5)
        years = [fdp.ConsumeIntInRange(2009, 2025) for _ in range(num_years)]

        num_months = fdp.ConsumeIntInRange(1, 12)
        months = [fdp.ConsumeIntInRange(1, 12) for _ in range(num_months)]

        result = generate_parquet_urls(datasets=datasets, years=years, months=months)

        _assert_valid_result(result, datasets, years, months)

    except EXPECTED_EXCEPTIONS:
        pass
    except Exception as e:
        raise e


# ── Estrategia 2: tipos errados nos campos ────────────────────────────────────


def fuzz_wrong_types(data):
    """
    Testa os type guards: bool no lugar de int, string no lugar de int,
    int no lugar de string, None nos iteraveis, etc.
    """
    fdp = atheris.FuzzedDataProvider(data)

    try:
        case = fdp.ConsumeIntInRange(0, 7)

        if case == 0:
            # bool e explicitamente rejeitado como year
            generate_parquet_urls(["yellow"], [True], [1])

        elif case == 1:
            # bool e explicitamente rejeitado como month
            generate_parquet_urls(["yellow"], [2023], [False])

        elif case == 2:
            # string no lugar de year
            generate_parquet_urls(["yellow"], [fdp.ConsumeUnicode(5)], [1])

        elif case == 3:
            # string no lugar de month
            generate_parquet_urls(["yellow"], [2023], [fdp.ConsumeUnicode(5)])

        elif case == 4:
            # int no lugar de dataset
            generate_parquet_urls([fdp.ConsumeInt(4)], [2023], [1])

        elif case == 5:
            # years=None deve lancar TypeError (None nao e iteravel)
            generate_parquet_urls(["yellow"], None, [1])

        elif case == 6:
            # months=None deve lancar TypeError
            generate_parquet_urls(["yellow"], [2023], None)

        elif case == 7:
            # float no lugar de month
            generate_parquet_urls(["yellow"], [2023], [fdp.ConsumeFloat()])

    except EXPECTED_EXCEPTIONS:
        pass
    except Exception as e:
        raise e


# ── Estrategia 3: valores fora do range ───────────────────────────────────────


def fuzz_out_of_range(data):
    """
    Testa meses fora de [1, 12] e datasets invalidos.
    """
    fdp = atheris.FuzzedDataProvider(data)

    try:
        case = fdp.ConsumeIntInRange(0, 3)

        if case == 0:
            # Mes > 12
            bad_month = fdp.ConsumeIntInRange(13, 100000)
            generate_parquet_urls(["yellow"], [2023], [bad_month])

        elif case == 1:
            # Mes < 1 (zero e negativos)
            bad_month = fdp.ConsumeIntInRange(-100000, 0)
            generate_parquet_urls(["yellow"], [2023], [bad_month])

        elif case == 2:
            # Dataset com string aleatoria (quase sempre invalido)
            bad_dataset = fdp.ConsumeUnicode(30)
            generate_parquet_urls([bad_dataset], [2023], [1])

        elif case == 3:
            # Mix: um valido e um invalido na mesma lista
            valid = fdp.PickValueInList(VALID_DATASETS_LIST)
            invalid = fdp.ConsumeUnicode(20)
            generate_parquet_urls([valid, invalid], [2023], [1])

    except EXPECTED_EXCEPTIONS:
        pass
    except Exception as e:
        raise e


# ── Estrategia 4: datasets=None (caminho especial) ────────────────────────────


def fuzz_none_datasets(data):
    """
    datasets=None deve sempre retornar exatamente 4 * years * months URLs.
    """
    fdp = atheris.FuzzedDataProvider(data)

    try:
        num_years = fdp.ConsumeIntInRange(1, 3)
        years = list({fdp.ConsumeIntInRange(2009, 2025) for _ in range(num_years)})

        num_months = fdp.ConsumeIntInRange(1, 12)
        months = list({fdp.ConsumeIntInRange(1, 12) for _ in range(num_months)})

        result = generate_parquet_urls(datasets=None, years=years, months=months)

        assert isinstance(result, list)

        expected = 4 * len(years) * len(months)
        assert len(result) == expected, (
            f"datasets=None: esperado {expected} URLs, recebeu {len(result)}"
        )

        # Todos os 4 datasets devem aparecer
        found_datasets = {url.split("/")[-1].split("_")[0] for url in result}
        assert found_datasets == VALID_DATASETS, (
            f"datasets=None deve conter todos os 4 datasets, recebeu: {found_datasets}"
        )

    except EXPECTED_EXCEPTIONS:
        pass
    except Exception as e:
        raise e


# ── Estrategia 5: listas vazias ───────────────────────────────────────────────


def fuzz_empty_inputs(data):
    """
    Listas vazias em qualquer parametro devem retornar [] sem crash.
    """
    fdp = atheris.FuzzedDataProvider(data)

    try:
        case = fdp.ConsumeIntInRange(0, 2)

        if case == 0:
            result = generate_parquet_urls([], [2023], [1])
            assert result == [], f"datasets=[] deve retornar [], recebeu {result}"

        elif case == 1:
            result = generate_parquet_urls(["yellow"], [], [1])
            assert result == [], f"years=[] deve retornar [], recebeu {result}"

        elif case == 2:
            result = generate_parquet_urls(["yellow"], [2023], [])
            assert result == [], f"months=[] deve retornar [], recebeu {result}"

    except EXPECTED_EXCEPTIONS:
        pass
    except Exception as e:
        raise e


# ── Entry point ───────────────────────────────────────────────────────────────


def test_one_input(data):
    """
    Roda todas as estrategias em cada execucao.
    O libFuzzer muta os bytes buscando aumentar cobertura em qualquer uma delas.
    """
    fuzz_valid_seeds(data)
    fuzz_wrong_types(data)
    fuzz_out_of_range(data)
    fuzz_none_datasets(data)
    fuzz_empty_inputs(data)


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
