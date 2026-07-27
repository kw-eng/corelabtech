# Umowa powierzenia przetwarzania danych - szablon

Wersja: 2026-07-26

> Dokument wymaga weryfikacji prawnej i dostosowania do rzeczywistych ról stron,
> hostingu, podprocesorów oraz transferów danych.

## 1. Role stron

Administrator: `[placówka wellness]`.

Podmiot przetwarzający: `[Dostawca CoreLabTech]`.

Podmiot przetwarzający działa wyłącznie na udokumentowane polecenie
Administratora, chyba że obowiązek przetwarzania wynika z prawa.

## 2. Przedmiot, czas, charakter i cel

- Przedmiot: hosting i utrzymanie platformy CoreLabTech.
- Czas: okres obowiązywania umowy głównej oraz kontrolowany okres zakończenia.
- Charakter: zbieranie, utrwalanie, organizowanie, synchronizacja, analiza,
  udostępnianie upoważnionym osobom, eksport, ograniczenie i usuwanie.
- Cel: realizacja usług dokumentowania i analizy sesji wellness.

## 3. Kategorie danych i osób

Dane klientów placówki mogą obejmować identyfikator, dane profilu, ankiety,
notatki, HR, HRV, SpO2, puls, czas, dane urządzenia, ciśnienie, protokół,
wskaźniki jakości, wyniki i raporty.

Osoby: klienci placówki oraz upoważnieni pracownicy.

## 4. Instrukcje i poufność

Przetwarzający zapewnia, że osoby mające dostęp do danych są upoważnione,
zobowiązane do poufności i przetwarzają dane tylko w zakresie swoich ról.

## 5. Bezpieczeństwo

Minimalne środki:

- TLS/HTTPS,
- kontrola ról i izolacja danych klienta,
- silne hasła i bezpieczne cookies,
- szyfrowane lub odpowiednio chronione backupy,
- audit log operacji administracyjnych,
- aktualizacje bezpieczeństwa,
- procedura obsługi incydentu i test restore,
- ograniczenie dostępu do PostgreSQL do sieci aplikacji.

## 6. Podprzetwarzający i transfery

Lista podprzetwarzających: `[hosting, e-mail, monitoring, backup]`.
Zmiana podprzetwarzającego wymaga procedury informacyjnej/sprzeciwu określonej
w umowie. Transfer poza EOG wymaga udokumentowanej podstawy i zabezpieczeń.

## 7. Prawa osób

Przetwarzający wspiera Administratora przy realizacji dostępu, sprostowania,
przenoszenia, ograniczenia i usunięcia. CoreLabTech udostępnia eksport ZIP JSON
oraz kontrolowane usunięcie klienta rejestrowane w audycie.

## 8. Naruszenia

Przetwarzający informuje Administratora bez zbędnej zwłoki, nie później niż
`[uzgodniony czas]`, po stwierdzeniu naruszenia oraz przekazuje dostępne
informacje potrzebne do oceny i zgłoszenia.

## 9. Zakończenie

Po zakończeniu świadczenia usług dane są, zgodnie z decyzją Administratora,
zwracane lub usuwane, chyba że prawo wymaga dalszego przechowywania.

## 10. Audyty

Przetwarzający udostępnia informacje niezbędne do wykazania zgodności i umożliwia
uzgodnione audyty z zachowaniem poufności oraz bezpieczeństwa innych klientów.

## Załączniki

- opis środków technicznych i organizacyjnych,
- lista podprzetwarzających,
- polityka retencji,
- procedura incydentowa,
- dane kontaktowe stron.
