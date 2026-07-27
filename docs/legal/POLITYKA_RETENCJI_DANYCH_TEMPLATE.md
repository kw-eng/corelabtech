# Polityka retencji danych CoreLabTech - szablon

Wersja: 2026-07-26

> Okresy są propozycją wdrożeniową. Administrator danych powinien zatwierdzić je
> po analizie celu, podstawy prawnej i lokalnych obowiązków.

| Kategoria | Proponowany okres | Działanie po okresie |
|---|---:|---|
| Profil aktywnego klienta | czas umowy/programu + 90 dni | eksport, usunięcie lub anonimizacja |
| Dane sesji i ankiety | 24 miesiące od ostatniej sesji | usunięcie lub anonimizacja |
| Surowe FIT/CSV i merged timeline | 12 miesięcy | usunięcie po zachowaniu agregatów |
| Raporty PDF | 24 miesiące | usunięcie |
| Zgody i ich wersje | okres usługi + wymagany okres dowodowy | ograniczenie dostępu, następnie usunięcie |
| Audit log | 24 miesiące | anonimizacja identyfikatora i usunięcie szczegółów |
| Backup operacyjny | 30 dni, rotacja | automatyczne nadpisanie |
| Eksport wygenerowany na żądanie | maks. 7 dni | bezpieczne usunięcie |

## Zasady

- Retencja jest konfigurowana i zatwierdzana osobno dla każdej placówki.
- Dane nie są przechowywane „na wszelki wypadek”.
- Usunięcie klienta obejmuje dane źródłowe, sesje, analizy i baseline.
- W audycie identyfikator usuniętego klienta jest zastępowany jednokierunkowym
  tokenem, bez zachowania pierwotnego identyfikatora.
- Backup nie służy do przywracania celowo usuniętego klienta do aktywnego systemu.
- Każda blokada usunięcia wynikająca z prawa lub sporu jest dokumentowana.

## Przeglądy

Właściciel polityki wykonuje co najmniej kwartalny przegląd rekordów, wyjątków,
backupów, żądań klientów i kont pracowników. Wynik przeglądu jest audytowany.
