import random
import re


def gera_numero(digitos: int = 4, decimais: int = 2) -> str:
    if digitos <= 0:
        inteiro = "0"
    elif digitos == 1:
        inteiro = str(random.randint(0, 9))
    else:
        primeiro = str(random.randint(1, 9))
        resto = "".join(str(random.randint(0, 9)) for _ in range(digitos - 1))
        inteiro = primeiro + resto

    if decimais > 0:
        dec_str = "".join(str(random.randint(0, 9)) for _ in range(decimais))
        return f"{inteiro}.{dec_str}"

    return inteiro


def gera_inteiro(digitos: int = 5, zerofills: int = 0) -> str:
    digitos_str = "" if digitos <= 0 else "".join(str(random.randint(0, 9)) for _ in range(digitos))
    zeros = "0" * max(0, zerofills)
    return f"{zeros}{digitos_str}"


def gera_nome(tipo: str = "humano") -> str:
    tipo = tipo.lower().replace("'", "").replace('"', "").strip()

    if not tipo or tipo in ("humano", "humanos", "pessoa", "pessoas"):
        prenomes = ["Mariana", "Carlos", "Fernanda", "João", "Ana", "Pedro", "Lucas", "Julia", "Marcos"]
        sobrenomes = ["Oliveira", "Santos", "Costa", "Silva", "Pereira", "Gomes", "Martins", "Almeida"]
        return f"{random.choice(prenomes)} {random.choice(sobrenomes)}"

    if tipo in ("animal", "animais", "pet", "pets"):
        animais = [
            "Capivara Dourada",
            "Lobo Guará",
            "Arara Azul",
            "Onça Pintada",
            "Tigre Siberiano",
            "Falcão Peregrino",
            "Raposa Vermelha",
            "Golfinho Rotador",
        ]
        return random.choice(animais)

    if tipo in ("coisa", "coisas", "objeto", "objetos", "produto", "produtos"):
        coisas = [
            "Cadeira Ergonômica",
            "Teclado Mecânico",
            "Monitor Ultrawide",
            "Garrafa Térmica",
            "Mochila Impermeável",
            "Luminária de Mesa",
            "Fone Bluetooth",
            "Relógio Inteligente",
        ]
        return random.choice(coisas)

    if tipo in ("empresa", "empresas", "companhia"):
        empresas = ["Vértice Soluções", "Horizonte Digital", "Alfa Tecnologia", "Nova Era Sistemas"]
        return random.choice(empresas)

    if tipo in ("cidade", "cidades", "lugar", "lugares"):
        cidades = [
            "São Paulo",
            "Curitiba",
            "Florianópolis",
            "Belo Horizonte",
            "Porto Alegre",
            "Rio de Janeiro",
        ]
        return random.choice(cidades)

    return f"{tipo.capitalize()} Fantástico"


def gera_email(dominio: str = "exemplo.com.br") -> str:
    prenomes = ["mariana", "carlos", "fernanda", "joao", "ana", "pedro", "lucas", "julia", "marcos"]
    sobrenomes = ["oliveira", "santos", "costa", "silva", "pereira", "gomes", "martins", "almeida"]
    nome = random.choice(prenomes)
    sobrenome = random.choice(sobrenomes)
    num = random.randint(1000, 9999)
    return f"{nome}.{sobrenome}.{num}@{dominio.lower().strip()}"


def gera_texto(tamanho: int = 80) -> str:
    if tamanho <= 0:
        return ""

    frases = [
        "Admodum accumsan disputationi eu sit. Vide electram sadipscing et per.",
        "Mussum Ipsum, cacilds vidis litro abertis.",
        "Per aumento de cachacis, eu reclamis.",
        "Paisis, filhis, espiritis santis.",
        "Cevadis im ampola pa arma uma pindureta.",
        "Suco de cevadiss, é um leite divinis, qui tem lupuliz, matis, aguis e fermentis.",
        "Interagi no mé, cursus quis, vehicula ac nisi.",
        "Casamentiss faiz malandris se pirulitá.",
    ]

    random.shuffle(frases)
    texto = " ".join(frases)

    while len(texto) < tamanho:
        texto += " " + random.choice(frases)

    return texto[:tamanho]


def resolve_dynamic_value(value: str | None) -> str:
    if value is None or not isinstance(value, str):
        return str(value) if value is not None else ""

    patterns = [
        (r"\$?(?:\{)?gera_numero\(([^)]*)\)(?:\})?", gera_numero, [int, int]),
        (r"\$?(?:\{)?gera_inteiro\(([^)]*)\)(?:\})?", gera_inteiro, [int, int]),
        (r"\$?(?:\{)?gera_nome\(([^)]*)\)(?:\})?", gera_nome, [str]),
        (r"\$?(?:\{)?gera_email\(([^)]*)\)(?:\})?", gera_email, [str]),
        (r"\$?(?:\{)?gera_texto\(([^)]*)\)(?:\})?", gera_texto, [int]),
    ]

    result = value
    for pattern, func, arg_types in patterns:

        def replacer(match: re.Match, _func=func, _arg_types=arg_types) -> str:
            args_str = match.group(1).split(",")
            parsed_args = []
            for i, arg in enumerate(args_str):
                arg_clean = arg.strip().replace("'", "").replace('"', "")
                if arg_clean:
                    if i < len(_arg_types):
                        if _arg_types[i] is int:
                            try:
                                parsed_args.append(int(arg_clean))
                            except ValueError:
                                parsed_args.append(0)
                        else:
                            parsed_args.append(arg_clean)
                    else:
                        parsed_args.append(arg_clean)
            return str(_func(*parsed_args))

        result = re.sub(pattern, replacer, result)

    return result
