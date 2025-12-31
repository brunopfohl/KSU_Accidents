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
Základní shlukovací metoda K-Means je často využívána pro svou rychlost a jednoduchost. Nedávná studie Wahyono et al. (2024) aplikovala K-Means pro identifikaci rizikových oblastí ve městě Depok. Ačkoliv metoda dokázala klasifikovat městské čtvrti do rizikových skupin, pro detailní identifikaci na silniční síti má zásadní nevýhody:
*   Předpokládá sférické (kruhové) tvary shluků, což neodpovídá lineárnímu charakteru silnic.
*   Je citlivá na odlehlé hodnoty (outliers) a vyžaduje předem známý počet shluků ($k$), který je u dopravních dat v neznámém prostředí obtížné určit.

### B) DBSCAN (Density-based clustering)
Jako vhodnější alternativa se v literatuře uvádí algoritmus DBSCAN (Ester et al., 1996). AlHashmi (2024) ve své disertační práci využil DBSCAN k úspěšné identifikaci nehodových hotspotů na rozsáhlém datasetu, přičemž ocenil schopnost metody pracovat se šumem. Kamh et al. (2024) však ve svém srovnání upozorňují, že ačkoliv je DBSCAN lepší než K-Means, v oblastech s proměnlivou hustotou sítě může být překonán hierarchickými metodami. Přesto zůstává preferovanou metodou pro:
*   **Libovolné tvary:** Dokáže identifikovat shluky kopírující tvar silnic (zatáčky).
*   **Práce se šumem:** Automaticky vylučuje ojedinělé nehody.

### C) Getis-Ord Gi* (Prostorová statistika)
Třetím klíčovým přístupem je statistická analýza hot spotů pomocí statistiky Getis-Ord Gi*. Alkhatni et al. (2023) demonstrovali použití této metody v kombinaci s KDE pro identifikaci zón, kde se nehody shlukují se statistickou významností. Na rozdíl od prostého shlukování tato metoda:
*   Zohledňuje prostorovou autokorelaci a dokáže určit p-hodnotu (p-value).
*   Rozlišuje "Hot Spots" (shluky vysokých hodnot) a "Cold Spots" (shluky nízkých hodnot), což je klíčové pro validaci výsledků.

## 3. Navržené řešení
Na základě rešerše bude v práci zvolen **hybridní přístup**, který kombinuje silné stránky výše uvedených metod:

1.  **DBSCAN (Segmentace):** Bude využit pro prvotní **prostorovou segmentaci**. Jeho úkolem bude definovat konkrétní shluky nehod (např. křižovatky, úseky), jelikož lépe než mřížkové metody reflektuje nepravidelné tvary silniční sítě.
2.  **Getis-Ord Gi* (Validace a Anomálie):** Pro ověření **statistické významnosti** a zejména pro detekci **časových anomálií** bude aplikována metoda Getis-Ord Gi* přímo na atribut relativní četnosti nočních nehod (tzv. night ratio). Tento postup umožní identifikovat prostorové shluky, kde je podíl nočních nehod statisticky významně vyšší než v okolí (resp. než je očekávaná hodnota).

## 4. Potřebná data
K řešení problému budou využita otevřená data Policie ČR, která jsou dostupná pro celou Českou republiku.
*   **Zdroj:** Portál nehod (nehody.policie.gov.cz) / Národní katalog otevřených dat (data.gov.cz).
*   **Dataset:** `nehody_202001-202512.geojson` (Data za Liberecký kraj).
*   **Klíčové atributy:**
    *   Geografické souřadnice (GPS) – pro prostorovou analýzu.
    *   Datum a čas – pro segmentaci den/noc.
    *   Příčina a následky (hmotná škoda, zranění) – pro případné váhování závažnosti nehod.

## 5. Citace použitých zdrojů
1.  **AlHashmi, M. Y. S. (2024).** Using Machine Learning for Road Accident Severity Prediction and Optimal Rescue Pathways. *RIT Theses*.
2.  **Alkhatni, F., et al. (2023).** Hotspots based on the crash frequency by Getis-Ord Gi* and network KDE Methods. *ResearchGate*.
3.  **Ester, M., et al. (1996).** A Density-Based Algorithm for Discovering Clusters in Large Spatial Databases with Noise. *KDD-96 Proceedings*.
4.  **Kamh, H., et al. (2024).** Exploring Road Traffic Accidents Hotspots Using Clustering Algorithms and GIS-Based Spatial Analysis. *ResearchGate*.
5.  **Wahyono, H., et al. (2024).** K-Means Clustering for Identifying Traffic Accident Hotspots in Depok City. *ResearchGate*.
