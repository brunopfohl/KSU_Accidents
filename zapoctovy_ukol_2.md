# Zadání 2. zápočtové úlohy: Analýza rizikových míst v dopravě a detekce časových anomálií

**Autor:** Bruno Pfohl  
**Téma:** Detekce nehodových hotspotů a časoprostorových anomálií (den/noc)

## 1. Definice problému
Cílem této úlohy je analýza prostorového rozložení dopravních nehod na území města Liberce se zaměřením na identifikaci rizikových lokalit (tzv. hotspotů). Práce si klade za cíl ověřit hypotézu, že nehodovost v určitých lokalitách není v čase konstantní, ale vykazuje specifické anomálie v závislosti na denní době.

Konkrétně se práce zaměří na detekci:
1.  **Dopravních hotspotů:** Míst s vysokou koncentrací nehod.
2.  **Časových anomálií:** Lokalil, kde je statisticky významně vyšší podíl nočních nehod oproti celkovému průměru (např. vlivem špatného osvětlení, nepřehlednosti), nebo naopak míst rizikových pouze ve dne (vlivem intenzity dopravy).

## 2. Rešerše přístupů (State of the Art)
V odborné literatuře se pro identifikaci rizikových míst v dopravě nejčastěji porovnávají metody shlukové analýzy (Unsupervised Machine Learning) a metody prostorové statistiky.

### A) K-Means (Centroid-based clustering)
Základní shlukovací metoda K-Means je často využívána pro svou rychlost a jednoduchost. Anderson (2009) ve své studii aplikovala K-Means pro klasifikaci nehodových hotspotů v Londýně. Ačkoliv metoda dokázala rozdělit data do skupin podle atributů, pro prostorovou identifikaci na silniční síti má zásadní nevýhody:
*   Předpokládá sférické (kruhové) tvary shluků, což neodpovídá lineárnímu charakteru silnic.
*   Je citlivá na odlehlé hodnoty (outliers) a vyžaduje předem známý počet shluků ($k$), který je u dopravních dat v neznámém prostředí obtížné určit.

### B) DBSCAN (Density-based clustering)
Jako vhodnější alternativa se v literatuře (např. Kumar et al., 2017; Ester et al., 1996) uvádí algoritmus DBSCAN. Tato metoda je pro dopravní analýzu preferována z několika důvodů:
*   **Libovolné tvary:** Dokáže identifikovat shluky, které kopírují tvar silnic, křižovatek a zatáček (neomezuje se na kruhy).
*   **Práce se šumem:** Automaticky identifikuje a vylučuje ojedinělé nehody (šum), které netvoří skutečný hotspot.
Studie potvrzují, že DBSCAN dosahuje přesnějších výsledků při identifikaci "černých míst" (black spots) než metody založené na mřížce nebo K-Means.

### C) Getis-Ord Gi* (Prostorová statistika)
Třetím klíčovým přístupem je statistická analýza hot spotů pomocí statistiky Getis-Ord Gi* (Ord & Getis, 1995). Na rozdíl od prostého shlukování (kde shluk je jen "hodně bodů u sebe") tato metoda testuje **statistickou významnost** (statistical significance).
*   Zohledňuje prostorovou autokorelaci a dokáže pomocí p-hodnoty (p-value) určit, zda je koncentrace nehod v daném místě statisticky významná, nebo zda jde o náhodný jev.
*   Umožňuje rozlišit "Hot Spots" (shluky vysokých hodnot) a "Cold Spots" (shluky nízkých hodnot).

## 3. Navržené řešení
Na základě rešerše bude v práci zvolen **hybridní přístup**:
1.  Metoda **DBSCAN** bude využita pro prvotní exploraci a definici tvaru rizikových úseků, jelikož nejlépe reflektuje topologii silniční sítě v Liberci.
2.  Pro ověření hypotézy o časových anomáliích (den vs. noc) bude aplikován **statistický přístup** (inspirovaný logikou Getis-Ord), který nebude porovnávat pouze absolutní počty nehod, ale testovat statistickou významnost odchylky poměru nočních nehod od očekávaného průměru.

## 4. Potřebná data
K řešení problému budou využita otevřená data Policie ČR, která jsou dostupná pro celou Českou republiku.
*   **Zdroj:** Portál nehod (nehody.policie.gov.cz) / Národní katalog otevřených dat (data.gov.cz).
*   **Dataset:** `nehody_202001-202512.geojson` (Data za Liberecký kraj).
*   **Klíčové atributy:**
    *   Geografické souřadnice (GPS) – pro prostorovou analýzu.
    *   Datum a čas – pro segmentaci den/noc.
    *   Příčina a následky (hmotná škoda, zranění) – pro případné váhování závažnosti nehod.

## 5. Citace použitých zdrojů
1.  **Anderson, T. K. (2009).** Kernel density estimation and K-means clustering to profile road accident hotspots. *Accident Analysis & Prevention*, 41(3), 359-364.
2.  **Ester, M., Kriegel, H. P., Sander, J., & Xu, X. (1996).** A density-based algorithm for discovering clusters in large spatial databases with noise. *KDD-96 Proceedings*.
3.  **Kumar, S., et al. (2017).** Black spot identification using cluster analysis. *International Journal of Civil Engineering and Technology*, 8(4).
4.  **Ord, J. K., & Getis, A. (1995).** Local Spatial Autocorrelation Statistics: Distributional Issues and an Application. *Geographical Analysis*, 27(4).