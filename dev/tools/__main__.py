"""The single entry point of the developer pipeline: python dev/run.py <command> [command arguments].

Commands are listed in the order they are run. Some work in the regular environment (build_env),
synthesis and stress marks in the environment with Holos TTS (holos_env). More: "python dev/run.py --help" and the README.
"""
import importlib
import sys

# command: (the module that runs it, a short description)
COMMANDS = [
    ("translate", "tools.text.translate", "чернетка перекладу локальною моделлю (потрібен запущений llama-server)"),
    ("fixes", "tools.text.fixes", "застосувати ручні правки dev/config/manual_fixes/*.jsonl до таблиці перекладу"),
    ("build", "tools.text.build", "зібрати loca_uk_texts.csv для гри з таблиці перекладу"),
    ("address-check", "tools.text.address_check", "звіт про змішування ти/ви"),
    ("address-fix", "tools.text.address_fix", "виправити ти/ви моделлю за правилом"),
    ("repass", "tools.text.repass", "повторний прохід моделі по рядках зі звіту review_uk.csv"),
    ("review", "tools.text.review", "вичитка: review dump <префікс> / review apply <префікс> <файл>"),
    ("validate", "tools.text.validate", "перевірити переклад у content/uk/loca_uk_texts.csv (розмітка, ремарки, огріхи)"),
    ("toolcheck", "tools.text.toolcheck", "записати/перевірити штамп toolcheck.json (контрольні суми файлів контенту й застосунку)"),
    ("sync", "tools.text.public", "імпорт правок і статусів із content/uk (pull request-и) у робочу таблицю; без таблиці відновлює її з контенту"),
    ("public", "tools.text.public", "статуси рядків у content/uk/status.csv (текст пише сама build); --clean далі видаляє робочу теку"),
    ("extract", "tools.game.extract", "розпакувати англійське озвучення з вашої гри (оригінали для довжин і мікшування)"),
    ("stress-words", "tools.voice.stress_words", "слова з кількома варіантами наголосу (для розв'язання омонімів)"),
    ("voice", "tools.voice.synth", "синтез реплік Holos TTS одразу в content/uk/audio (Ogg Opus), оновлює індекс і manifest.json (середовище holos_env)"),
    ("install", "tools.game.deploy", "встановити content/ у вашу гру (як вікно інсталятора): послухати результат після voice; --no-voice, --no-mix, --force"),
    ("uninstall", "tools.game.deploy", "прибрати українську мову з теки гри й повернути оригінали"),
    ("clean", "tools.clean", "видалити робочу теку конвеєра (усе потрібне відновлюється з content/)"),
    ("release", "tools.game.release", "зібрати три файли релізу контенту (manifest.json, loca_uk_texts.csv, voice.zip); перед цим оновлює індекс і manifest.json"),
]


def usage():
    print(__doc__)
    for name, _, what in COMMANDS:
        print(f"  {name:<14} {what}")


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        usage()
        return 0
    table = {name: mod for name, mod, _ in COMMANDS}
    if argv[0] not in table:
        print(f"Невідома команда: {argv[0]}\n")
        usage()
        return 2
    if argv[0] != "clean":
        from tools import paths
        paths.ensure_work()            # the work folder (outside the repository) with its marker
    mod = importlib.import_module(table[argv[0]])
    sys.argv = [f"python dev/run.py {argv[0]}"] + argv[1:]
    return mod.main() or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
