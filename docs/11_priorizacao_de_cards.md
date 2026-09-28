# Modelo de Regras para Reordenação de Cards

Documento de referência reutilizável. Use sempre que precisar reordenar um backlog
de forma **determinística** (o mesmo conjunto de cards sempre produz a mesma ordem,
independentemente de quem executa ou de quando).

Este modelo é **neutro**: não acopla a nenhum projeto, ferramenta ou cliente. Os
campos citados são os do Jira apenas porque é o ambiente em que foi validado; em
outra ferramenta, mapeie cada campo para o equivalente local.

---

## 1. Princípio

A ordem de prioridade é o resultado de aplicar **três critérios em sequência**.
Aplica-se o primeiro critério; ele separa o grupo. Só dentro dos grupos que ficaram
empatados aplica-se o segundo. E assim por diante.

> Regra de ouro: **nunca inventar um critério que não esteja escrito aqui.**
> Se a ordem desejada não pode ser obtida, o problema é a falta de dado nos cards
> (seção 6), não a regra.

---

## 2. Os três critérios

### Critério 1 — Classe: Bug antes de Feature

Cards que corrigem algo **quebrado** têm precedência sobre cards que **construem**
algo novo.

| Grupo | O que entra |
| :--- | :--- |
| **1º (frente)** | `Bug` — defeito, erro, regressão, comportamento incorreto |
| **2º** | `História` / `Tarefa` de produto — funcionalidade nova, melhoria, refatoração |

Se os dois grupos coexistirem, **todo** bug sai à frente de **todas** as features,
independentemente de idade ou urgência.

### Critério 2 — Urgência: mais urgente antes de menos urgente

Dentro do mesmo grupo, a urgência do próprio Jira manda. A ordem canônica é a do
próprio esquema de prioridades:

```
Highest > High > Medium > Low > Lowest
```

Card **sem prioridade definida** herda o nível mais baixo do grupo, para não ganhar
vantagem por omissão. Se a sua organização usa *due date* ou *flag* de urgência em
vez do campo de prioridade, substitua a lista acima por essa — mas mantenha a mesma
regra de card sem sinal herdar o pior nível.

### Critério 3 — Idade: mais antigo antes de mais recente

Critério final, puramente cronológico. Maior tempo de permanência no backlog vence.

```
created ASC  →  o card criado há mais tempo fica na frente
```

A idade só é consultada quando o card **já empatou** nos critérios 1 e 2. Ela nunca
promove um bug antigo acima de um bug novo que seja mais urgente.

---

## 3. Desempate absoluto

Se dois cards empatarem nos três critérios, use esta ordem:

1. **Maior tempo no status atual** vence (card mais "`A fazer`" há mais tempo).
2. **Maior número de bloqueadores abertos** vence (card mais travado sobe).
3. **Chave do card em ordem crescente** — desempate puramente estável, para que a
   ordenação continue reprodutível.

---

## 4. Como obter a lista já ordenada no Jira

O JQL **não** permite ordenar por tipo de issue. A solução prática é rodar duas
consultas e concatená-las, porque a própria separação em duas filas já implementa o
Critério 1:

```jql
-- Fila 1: bugs, do mais urgente ao mais antigo
project = GTE
  AND statusCategory != Done
  AND issuetype = Bug
ORDER BY priority DESC, created ASC

-- Fila 2: features, do mais urgente ao mais antigo
project = GTE
  AND statusCategory != Done
  AND issuetype != Bug
ORDER BY priority DESC, created ASC
```

A ordem final é **Fila 1 inteira, depois Fila 2 inteira**.

> **Validar uma vez na sua instância:** o sentido de `priority DESC` varia conforme a
> configuração do esquema de prioridades. Abra os dois resultados e confirme se
> "Highest" realmente vem primeiro. Se vier invertido, troque para `priority ASC`.

---

## 5. Exemplo trabalhado

Backlog com 5 cards:

| Card | Tipo | Prioridade | Criado | Posição | Critério que decidiu |
| :--- | :--- | :--- | :--- | :--- | :--- |
| A | Bug | Medium | 01/01 | **1** | Classe (bug) |
| B | Bug | Highest | 20/01 | **2** | Classe; B depois de A por urgência |
| C | Tarefa | High | 05/01 | **3** | Classe (feature) começa aqui |
| D | Tarefa | High | 02/01 | **4** | Igual a C; D é mais antigo |
| E | Tarefa | *sem prioridade* | 03/01 | **5** | Sem prioridade herda o pior nível |

Leitura: A e B são bugs, então passam à frente de C, D e E. Entre os bugs, B é
`Highest` e A é `Medium`, logo B fica na frente **apesar de ser 19 dias mais novo**.
Entre as features, C e D empatam em prioridade, e D vence por ser mais antigo. E
perde para C e D por não ter prioridade, e para D também por ser mais nova.

---

## 6. Pré-requisitos de higiene

A ordenação só tem força se os cards carregarem os dados que os critérios leem.
Verifique periodicamente:

- [ ] **Todo card de defeito tem `issuetype = Bug`.** Card de defeito cadastrado
      como "Tarefa" furta a frente de todas as features sem precisar ser urgente.
- [ ] **Todo card tem prioridade definida.** Sem ela o Critério 2 não separa nada e
      todo o backlog colapsa no Critério 3, virando ordem cronológica.
- [ ] **Nenhum card de teste/placeholder no backlog** (resumos como "teste", "abc").
      Não é bug nem feature: não pertence a nenhuma fila. Arquive antes de ordenar.
- [ ] **Todo card tem responsável.** Card sem dono é o principal gargalo na prática,
      mesmo que a ordenação o coloque bem na frente.

Quando esses quatro itens estão garantidos, os três critérios passam a produzir
ordens realmente distintas. Quando não estão, a ordem "vira só data" — e isso é um
sinal de deuda de dados, não de regra ruim.

---

## 7. Como ajustar este modelo

- **Quer Bugs acima de Features mesmo quando a feature for urgente?** O Critério 1
  já garante isso. Não é preciso mudar nada.
- **Quer Features antes de Bugs** (ex.: roadmap de produto)? Remova o Critério 1 e
  promova Idade a Critério 1, renumerando os demais.
- **Quer ponderar por esforço?** Insira um novo critério entre 2 e 3. Nunca
  coloque esforço antes de Bug: esforço é o *tamanho* do trabalho, não o seu *impacto*.
- **Quer um 4º critério?** Acrescente-o ao final e renumere. Critérios novos só
  entram como desempate, para não invalidar a ordem já comunicada ao time.

Ao editar, atualize também o exemplo da seção 5 — ele é o contrato de comportamento
do modelo e é o que impede o documento de divergir da prática.
