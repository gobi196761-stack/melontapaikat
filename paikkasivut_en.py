"""Paikkasivujen englanninkieliset tekstit (/paikka/<tunniste>?kieli=en).

Käännökset paikkasivut.py:n suomenkielisistä kuvauksista (KUVAUKSET), lähtö- ja
loppupaikoista (LAHTO_LOPPU, samassa järjestyksessä; sijainnit tulevat suomenkielisestä)
ja paikat.py:n kohteiden huomioista (HUOMIOT: kohteet järjestyksessä, vain huomiolliset).
Lähteiden nimet jäävät alkuperäiskielelle.
"""

from __future__ import annotations

from paikkasivut import Kuvaus

KUVAUKSET: dict[str, Kuvaus] = {
    "Kipinä (Iijoki)": Kuvaus(
        "Kipinänkoski on a rapid on the Iijoki river in Pudasjärvi and a regular haunt of many Oulu "
        "paddlers: there is something to paddle all summer, the river is easy to reach and the "
        "eddies are clear. The waves and holes are not the biggest in Finland, but the rapid is "
        "excellent for keeping up your skills, and swims are usually not dangerous. Ice moves the "
        "rocks around, so the play spots change every few years.",
        (
            ("Getting there",
             "About 45 minutes from Oulu: about 60 km along the Kuusamo road (Kuusamontie), then "
             "left to the village of Kipinä. After a couple of kilometres the road crosses the "
             "Iijoki – the rapid is under the bridge. You can leave the car at the bus stop just "
             "past the bridge. From the boat landing below the rapid you walk back across the field."),
            ("Play spots",
             "The middle bridge opening is the best play spot at Kipinä. The hole that formed beside "
             "it in 2020 worked excellently at Pudasjärvi gauge readings of 107.7–108.1 m. At 107.7 "
             "m it is already shallow below the hole, and your helmet and paddle may hit the bottom. "
             "Do your stern squirts on the outer edge of the hole, because the pillar side is "
             "shallow. Above 107.85 m a narrow but easily surfable wave section appears on the outer "
             "edge of the hole. The eddy below the bridge pillar is long and calm.\n\n"
             "At high water (108.1–108.9 m) a slow surf wave forms in the rightmost bridge opening "
             "next to the bank; as the water drops it becomes more hole-like. There is no eddy, but "
             "the carry back is only 2–20 metres. Below 108.1 m it is too shallow under the wave.\n\n"
             "The lower waves are the most traditional play spots at Kipinä, but the spring flood of "
             "2018 made the whole wave train clearly shallower. The first wave can be surfed in a "
             "playboat at about 107.3–107.8 m. Before 2018, 107.25 m was already excellent for wave "
             "moves; nowadays you have to lean hard forward at that level. In longer kayaks the "
             "first and second waves can be surfed below 107.3 m, down to 106.8 m. Below 107.7 m you "
             "can get onto the first wave from the surfer's left eddy, but it is challenging; from "
             "the right eddy you can reach both waves below 107.4 m. The lower waves also suit "
             "whitewater SUP."),
            ("Water levels",
             "During the spring flood Kipinä is flat and getting onto the waves is hard work, but "
             "things improve once the water drops. Follow the Pudasjärvi water level gauge: Kipinä's "
             "own calculated discharge figures are not based on a gauge and are not reliable. "
             "Up-to-date information is also available from Pohjolan Voima, tel. +358 50 313 3306."),
        ),
    ),
    "Koiteli (Kiiminkijoki)": Kuvaus(
        "Koiteli and Tulikurkku, about 400 m upstream of it, are on the Kiiminkijoki river in "
        "Kiiminki, about a 25-minute drive from Oulu. There are no mega-waves or big play holes, but "
        "with an open mind you can find small play spots in every channel at different water levels, "
        "and the rapid is good for practising river running. There is usually enough water until "
        "early June, and longer in rainy summers. At peak flood the rapid has very sticky pour-overs "
        "– at the 2010 flood peak on 20 April the water level was about 11.6 m and the discharge 250 "
        "m³/s.",
        (
            ("Play spots",
             "Tukkiränni (the far channel, an old log flume) is fun to run because of its big waves. "
             "Fairly low down a surf wave forms at both high and low water, and at about 10.5 m also "
             "a surf wave in the middle of the rapid.\n\n"
             "Takaköngäs is in the side channel behind Tukkiränni, right under the bridge: a small "
             "hole, similar to the one at Taivalkoski, forms below a drop of about a metre. It plays "
             "well at about 11.0 m and below. At 10.5 m the hole is still deep in the middle, but "
             "you hit rocks at the edges.\n\n"
             "Etuaalto and Helmihontto work at least at 10.3–11.0 m. Etuaalto is in the middle of "
             "the rapid, the first spot when paddling downstream from the car park. Looking "
             "downstream, its right side is hole-like, and already at 10.4 m you can cartwheel and "
             "loop there. Helmihontto is downstream of the wave on the right, by the shore of the "
             "island, and at its best at 10.7 m. As the water drops it becomes more flushy but stays "
             "paddleable. The small pour-over behind the hole is not dangerous. It slows the current "
             "so that you easily make it to the eddy. The hole is good for practising cartwheels, "
             "split wheels, loops and space godzillas, but it is not very sticky, so your moves have "
             "to be precise.\n\n"
             "Tulikurkku can only be reached by paddling. Carry the kayak over Tukkiränni along the "
             "bridge and follow the shore path upstream to the field from which you can see "
             "Myllysaari island. Paddle across the first channel to below the island and upstream "
             "along the island's shore. A small wave with a good eddy forms in the narrow gap "
             "between the rocks. It is sensitive to the water level and at its best at 10.7 m; as "
             "the water drops the wave gets smaller, but the spot stays good for practice. Unlike "
             "the other Koiteli spots, Tulikurkku also suits beginners."),
            ("Experiences",
             "In spring 2010 the Finnish freestyle team considered Koiteli the best training spot in "
             "Northern Ostrobothnia, because Taivalkoski had too much water, Hawa'Ii too little, and "
             "the Tornionjoki was not yet accessible. After the water dropped a new spot, "
             "Helmihontto, was found (SYKE 10.5.2010: Haukipudas 10.66 m, 117 m³/s), and over the "
             "Ascension Day weekend the far step had a sticky hole good for cartwheels, with eddies "
             "on both sides (SYKE 13–16.5.2010: Haukipudas 10.61–10.54 m, 108–97 m³/s)."),
        ),
    ),
    "Matkakoski (Tornionjoki)": Kuvaus(
        "Matkakoski on the Tornionjoki in Ylitornio is a classic of the border river, and there is "
        "always something to paddle there. The spring flood is a chapter of its own: you will hardly "
        "find as much water, or as big waves and holes, anywhere else in Finland – 'Zambezi style', "
        "especially if you put in 6 km upstream at Vuennonkoski. The actual play season is in late "
        "summer and autumn, when the river is at its lowest.",
        (
            ("Water level and play spots",
             "You can recognise a flood by the rock in the middle of the rapid: if it is not "
             "visible, the water is above 31 m (500 cm on the old automatic gauge). Above 28 m "
             "(automatic gauge 190–200 cm) you drop into the play spots from above and cannot paddle "
             "back – you have to carry. The best time starts when the water drops below 28 m (180 "
             "cm) and you can paddle back to the spots; the ideal reading is about 27.5–27.8 m.\n\n"
             "In the play season there is a big hole, about 15–20 metres wide, at the top of the "
             "Finnish side and a big, fast wave in the Swedish channel. The Finnish channel has a "
             "smaller hole, and right by the Finnish bank there is a small WC-Duck-type pour-over "
             "hole. When the automatic gauge shows 93–140 cm, the Swedish wave gets worse, but the "
             "upper hole plays even with little water. The Varsakallio hole is 'quite manly' (2010)."),
            ("Hazards",
             "Not for beginners or for poorly fitting spray decks – there are dangerous places. "
             "Watch out especially around the rock in the middle of the rapid, particularly on the "
             "Swedish side. A swim will be a long one. As the water drops, the Swedish edge of the "
             "big hole turns into a dangerous-looking pit, and ropes used for scooping can cause "
             "trouble."),
            ("Experiences",
             "On 25 May 2010 the discharge was about 2300 m³/s (SYKE 25.5.2010: Matkakoski 30.98 m, "
             "Karunki 2568 m³/s). Vuennonkoski had house-sized waves and dark whirlpools, and "
             "according to the blog Matkakoski offered 'the biggest mess you can find in Finland': "
             "the surfs were mostly a fight for survival. In September 2010 (27.7 m, about 335 m³/s) "
             "the Swedish wave was difficult, and in October (27.2 m, about 210 m³/s) the hole was "
             "good for loops.\n\n"
             "The autumn rains of 2009 raised the water just right for the Swedish wave (SYKE "
             "20.9.2009: Matkakoski 27.64 m, Karunki 341 m³/s): 'on a good day it puts a smile on a "
             "paddler's face, on a bad day it breaks the self-esteem of even the best paddler'. In "
             "May 2014 the wave season was opened on the Swedish wave right after the ice went out "
             "(SYKE 4–11.5.2014: Matkakoski 28.38–28.05 m, Karunki 697–471 m³/s), and in July 2014 "
             "both the Swedish and the Finnish waves worked (SYKE 7.7.2014: Matkakoski 28.09 m, "
             "Karunki 478 m³/s). Both required carrying, but it was worth it."),
        ),
    ),
    "Kattilakoski (Tornionjoki)": Kuvaus(
        "At high water Kattilakoski on the Tornionjoki is the best freestyle spot in Finland: 'There "
        "is so much to paddle at Kattilakoski that your stamina won't last.' You drive there from "
        "Övertorneå about 20 km upstream along the Swedish side of the river; at the rapid there is "
        "a restaurant, a car park and warm toilets. It is about 230 km from Oulu. The rapid starts "
        "at the restaurant, and the last play spot is about 1.5 km further down, which you can also "
        "reach by car (heading back from the put-in, the first road to the left, sign Maunu). The "
        "rapid only works with high enough water: the season is during the spring flood, and by July "
        "it is hardly worth the trip.",
        (
            ("Play spots from top to bottom",
             "Hevosenkenkä (the Horseshoe): at flood the Swedish channel by the rock island at the "
             "top of the rapid has a really manly horseshoe-shaped hole the width of the whole "
             "channel, with a big tongue in the middle. As the water drops it becomes a good play "
             "spot where cartwheels and loops work. At the right level a small second wave forms "
             "behind the hole; it is very sensitive to changes in the water level and crashes to the "
             "bottom if there is too much water. At the right level every wave move works on it.\n\n"
             "At flood, at the lower end of the island on the Swedish side, there is a mystery hole "
             "that sometimes disappears completely and reappears a moment later. The island's "
             "Finnish channel has a fast, breaking mega-wave 'where things happen'. Halfway down the "
             "rapid on the Finnish side there is a big drop that is worth scouting before running "
             "it; below it forms a medium-sized, quite sticky hole.\n\n"
             "Finnvågen is about half a kilometre down from the top of the rapid on the Finnish "
             "side: a big, fast wave that needs a lot of water and disappears as the water drops. At "
             "high water you can only get back by carrying. On the Swedish edge there is the car "
             "park hole (Parkkihontto), which you can drive right up to – a really good training "
             "spot at high water. On the Swedish bank by the car park there is also the sausage hole "
             "(Makkarahontto; needs a lot of water, suits beginners). Further down, by the barbecue "
             "hut, there is a small hole where you can spin and cartwheel. The last good spot is the "
             "lower wave (Ala-aalto) in the main current on the Finnish side of the rock island; at "
             "its best it is soft, gently sloping and sticky, and you get onto it via a side wave.\n\n"
             "The Svanstein hole is about 14 km upstream, above the village of Svanstein. Start from "
             "the swimming beach opposite the church, paddle upstream and ferry over to the edge of "
             "the island, from where the eddy takes you to the hole (between the island and the "
             "Swedish bank). The spot suits all levels and is excellent for practising hole "
             "paddling."),
            ("Hazards and tips",
             "The edges of the hole at the top of the rapid have a strong backwash: if you lose "
             "control, a swim is coming. The drop on the Finnish side halfway down the rapid can be "
             "dangerous if run from the wrong place. Otherwise swimming is relatively safe, because "
             "the eddies are big and you have time to collect your gear. If you rest your legs on "
             "the middle rock, pull your kayak well above the waterline – the swell can take your "
             "gear. In spring, ice can come through the wave."),
            ("Experiences and floods",
             "In May 2010 the season was opened in a heatwave: the Horseshoe's second wave was at "
             "just the right level (SYKE 15.5.2010: Pello 78.23 m, 845 m³/s), and on 17 May the "
             "lower wave and the mega-wave were at their best (SYKE 17.5.2010: Pello 78.84 m, 1290 "
             "m³/s). The next day there was too much water for the lower wave, but the mega-wave "
             "still worked (SYKE 18.5.2010: Pello 79.17 m, 1550 m³/s). The 2011 Finnish freestyle "
             "championships were held at Kattilakoski in the barbecue hut hole, when the lower wave "
             "was just centimetres short (SYKE 28.5.2011: Pello 78.88 m, 1325 m³/s). In May 2012 "
             "Finnvågen only worked for a day, because the water stayed lower than forecast (SYKE "
             "21.5.2012: Pello 80.17 m, 2400 m³/s).\n\n"
             "In May 2023 the Tornionjoki had the biggest flood in its measurement history (SYKE "
             "18–20.5.2023: Pello 80.53–81.39 m, 2730–3630 m³/s). Finnvågen was more than three "
             "metres high, but its typical constant pumping even increased above 3000 m³/s, and at "
             "3500 m³/s the wave at times acted as an aggressive hole. About 2850 m³/s turned out to "
             "be best, but even then the magic moments required minutes of surfing and the right "
             "timing. According to osm.fi, the best surfs have been had at discharges above 3000 "
             "m³/s."),
        ),
    ),
    "Kukkolankoski (Tornionjoki)": Kuvaus(
        "Kukkolankoski is on the Tornionjoki about 15–20 km from Tornio towards Ylitornio. It is a "
        "big-wave rapid of impressive size – the opposite bank is several hundred metres away – and "
        "mostly a place for running rather than playing. There are few play spots, especially at "
        "high water. The rapid is known for scoop-net fishing of whitefish, and there are services "
        "on both banks: on the Swedish side the Kukkolaforsen campsite with restaurants and saunas, "
        "on the Finnish side Koskipirtti and a café.",
        (
            ("Play spots",
             "At the top of the rapid on the Finnish side there is a long rock, and a play spot "
             "forms on each side of it when the Matkakoski water level is 28–28.7 m (old automatic "
             "gauge 200–270 cm). The small hole on the Finnish edge is good for spinning, but it "
             "does not hold you for vertical moves, the eddy is short and there are two shallow "
             "holes below, so you have to roll quickly. On the Swedish edge of the rock there is a "
             "good surf wave, but the eddy is really short. At 29.2 m (320 cm) there is too much "
             "water. The lower part of the rapid has big waves, and the big, slightly breaking wave "
             "in the middle gives good surfs if you dare."),
            ("Running the rapid",
             "You can carry the kayaks from the Koskipirtti car park along the shore to the top of "
             "the rapid (ask the residents of the house for permission) or drive a good hundred "
             "metres past Koskipirtti to the road leading to the shore, which ends at an old customs "
             "guard hut. The first time, line up on the right side of the rock at the top (looking "
             "upstream) and stay fairly close to the left bank: there are holes right by the bank, "
             "but 5–10 m further out there is a good line. If you swim at the top, it can be a long "
             "swim. The play spots are tricky for beginners, but even less experienced paddlers can "
             "run the rapid.\n\n"
             "In July 2017 Tuus-Melojat ran the rapid from Sweden to Finland for ice cream and back: "
             "first into shelter behind the first island after a small drop, and then straight "
             "across to the opposite bank before the current takes you too far down. Towards the end "
             "of the run there were great high waves."),
            ("Experiences",
             "In July 2014 national team paddlers surfed the 'Gladiator wave' (SYKE 9.7.2014: "
             "Matkakoski 28.20 m, Karunki 513 m³/s): hole and wave moves worked on the slow, small "
             "wave, but it was best for spinning. The spot is a nice change with eddies after "
             "Matkakoski."),
        ),
    ),
    "Vuentokoski (Tornionjoki)": Kuvaus(
        "Vuennonkoski is on the Tornionjoki about 6 km upstream of Matkakoski. It has big waves and "
        "holes but no eddies, so you drop into the holes and waves from above – look first where you "
        "are going. The put-in is at the campsite, which is signposted from the road in summer. The "
        "stretch from Vuennonkoski to Matkakoski is almost entirely moving water: a good, fast river "
        "run.",
        (
            ("Water levels",
             "At a Matkakoski water level of 28.7 m the stretch has nice play spots, but at 28.2 m "
             "it is hardly worth running anymore. During the flood the Vuento–Matkakoski stretch is "
             "'an exciting place'. Tuomas Vaarala described the run on 25 May 2010 (about 31 m, 2300 "
             "m³/s; SYKE 25.5.2010: Matkakoski 30.98 m, Karunki 2568 m³/s) as one of the best "
             "big-water runs in Finland: house-sized waves for starters, big holes that were avoided "
             "from far away, and rather sinister-looking whirlpools."),
        ),
    ),
    "Hawa'Ii (Iijoki, Maalismaa)": Kuvaus(
        "Hawa'Ii is a flood-season wave in the old channel of the Iijoki at the Maalismaa power "
        "plant in Yli-Ii. At flood a big, breaking wave forms in the channel, and as the water drops "
        "it becomes more hole-like. Thanks to its good eddy and even shape it is a great training "
        "spot – but don't paddle here if your roll is not reliable.",
        (
            ("Water levels",
             "When the Maalismaa discharge is 600 m³/s or a little below, the bow starts hitting "
             "rocks at the bottom of the wave. At 850 m³/s the spot is really good and gets better "
             "as the water rises, although getting to the eddy gets harder at the same time. In May "
             "2015 the discharge stayed at about 1150 m³/s for three days (SYKE 15–17.5.2015: "
             "Maalismaa 1136–1158 m³/s), and according to the blog it seemed optimal: 'I've paddled "
             "quite a few good waves, but never one this good!' About 900 m³/s (SYKE 11.5.2015: "
             "Maalismaa 898 m³/s) and about 700 m³/s (SYKE 17.5.2023: Maalismaa 720 m³/s) were also "
             "good. The two best parts of the wave: up from the green corner and down from closer to "
             "the middle. The next weir downstream has an impressive hole, but it has not seemed "
             "dangerous at 600–850 m³/s; you should be able to swim to the bank before it."),
            ("Getting there",
             "Drive from Ii towards Yli-Ii and turn towards Maalismaa just before the iron bridge "
             "over the Iijoki. Drive 16 km, and as soon as the road has crossed the power plant, "
             "turn left onto Voimalatie. Voimalatie curves to the right, but continue straight along "
             "the dirt track: the play spot is on the right right next to the track. The car park is "
             "on the isthmus between the old channel and the power plant's tailrace, at the wave."),
            ("Experiences",
             "The wave came back in May 2012 after a break of a few years (SYKE 5.5.2012: Maalismaa "
             "888 m³/s), and the national team stayed at the Maalismaa school for a week. The 2013 "
             "season was opened on 28 April with ice still floating in the eddy, a full-face helmet "
             "needed (SYKE 28.4.2013: Maalismaa 789 m³/s). In spring 2010 the water did not rise, "
             "and the trough of the wave stayed shallow (SYKE 10.5.2010: Maalismaa 448 m³/s)."),
        ),
    ),
    "Pyhäjoki": Kuvaus(
        "The Pyhäjoki has two play spots, both short-season spring spots. According to osm.fi, the "
        "colour and smell of the water are 'interesting'. The gauge is the Tolpankoski discharge.",
        (
            ("Ruukinkoski",
             "In the southern branch of Ruukinkoski, right below highway 8, there is a medium-sized "
             "hole that breaks into a wave at one end (it resembles the middle bridge opening spot "
             "at Kipinä). It works when the Tolpankoski discharge is 45–75 m³/s. The eddy is on "
             "river right, and you can paddle back to the spot. It is a little over 100 km from "
             "Oulu. A good spot to open the season."),
            ("Saunaranta wave",
             "Halfway down Pyhänkoski, next to a lakeside sauna, there is a breaking wave bigger "
             "than Ruukinkoski (partly a hole at low water). The eddy is on river right, but you "
             "usually have to carry back to the wave a few metres over a rocky isthmus. It works at "
             "about 80–150 m³/s and is perhaps at its best at about 140 m³/s; 170 m³/s is too much, "
             "when the wave doesn't hold and is skewed. About 125 km from Oulu.\n\n"
             "You can still run the rapid at high water. Above the bridge, where the current pushes "
             "against the rock, there are a couple of nasty-looking 'eddies' in hollows in the rock "
             "– beware. If you swim, the gear is collected from the pool about 1 km below the "
             "bridge."),
        ),
    ),
    "Siikajoki (Pöyryn pato)": Kuvaus(
        "The Siikajoki has several play spots; the most versatile area is right below the Pöyry "
        "power plant dam between Revonlahti and Siikajoenkylä. According to osm.fi the river appeals "
        "to all the senses: the water varies in colour and has a rural smell, so bring a nose clip "
        "and earplugs. Smaller rapids continue down to Siikajoenkylä.",
        (
            ("Getting there and putting in",
             "Coming along the road on the north side, a road end suitable for parking is at the end "
             "of the dam next to the fish ladder. You get on the water with the kayak on your "
             "shoulder, balancing on the rocks of the fish ladder. The dam prevents a normal spring "
             "flood and ice erosion, so the banks and eddies are bushy. You walk back to the car "
             "below the rapids along the edge of the field and the road, or you can leave a shuttle "
             "car lower down on the north side road."),
            ("Vaahtokylpy",
             "Vaahtokylpy (the Bubble Bath) in the river-right channel works over a wide range of "
             "water levels. Above 300 m³/s it is a downward-breaking wave and at its best at really "
             "high water, 300–400 m³/s (above 20.5 m). It still works at 250 m³/s, when the paddle "
             "and sometimes even your head hit the bottom when rolling. Thanks to an excellent eddy "
             "(on river left) the spot also suits less experienced paddlers, and a swimmer can be "
             "pulled in below the island.\n\n"
             "Below 250 m³/s (at least 140–250 m³/s, 19.7–20.4 m) the wave is too shallow, but a new "
             "wave forms on the other side of the tongue. At about 250 m³/s it has little grip and "
             "is a bit skewed, and at 150 m³/s it has turned into a hole from the bank, with plenty "
             "of depth for example for loops. The eddy by the bank (on river right) is short, but "
             "you can get back by paddling through the brush."),
            ("Other spots",
             "At the rock island above Vaahtokylpy, reasonable play spots form on both sides of the "
             "main current at 70–250 m³/s. At the lowest water, the small wave and hole at the "
             "island's lowest step work; you can still spin and cartwheel there at 70 m³/s. At low "
             "water there are nice eddy lines here for less experienced paddlers.\n\n"
             "About 5 km downstream of the dam there is a great wave that works at least above 150 "
             "m³/s. You have to carry to it, and at some levels it easily throws the surfer out to "
             "the right. In the centre of Ruukki, a big hole forms below the dam on the north bank "
             "in a big flood; don't go into it unless you know exactly what you are doing."),
        ),
    ),
    "Niskakoski (Lestijoki)": Kuvaus(
        "Niskankoski on the Lestijoki is halfway between Kannus and Himanka, next to a car park. It "
        "is one of the spots that open the whitewater season: head here in early April.",
        (
            ("Play spots",
             "The hole works when the discharge is above 50 m³/s. It is slightly skewed, but basic "
             "hole moves work. Above 85 m³/s a reasonable wave forms behind the hole. The eddies are "
             "good on both sides of the river, but at higher water the eddy lines can be tricky."),
        ),
    ),
    "Neitikoski (Lieksanjoki)": Kuvaus(
        "Neitikoski on the Lieksanjoki at Ruunaa is very popular among freestyle paddlers. Halfway "
        "down the rapid there is a wave or a hole almost the width of the river, depending on the "
        "water level – usually a breaking wave with an easily surfable tongue. The wave usually lets "
        "go of a capsized paddler or a swimmer quickly. The rapid ends in a lake, so swims are "
        "short, gear is easy to collect and it is easy to get back to the play spot. The rapid is "
        "about 200 m long, with a drop of 1 m.",
        (
            ("Water levels",
             "At flood the wave can break across its whole width almost to the bottom and be tricky "
             "for those with little experience. According to koskimelonta.com, above 110 m³/s "
             "(bridge gauge about 8) the wave breaks to the bottom: wave moves require explosive "
             "paddling, but it is excellent for practising loops. Above 120 m³/s (jetty gauge about "
             "9.5) the wave gets steeper and wave moves are easier. Below 100 m³/s a hole forms by "
             "the forest edge and a tongue in the middle, and at low water the left edge of the play "
             "spot turns into a hole. You can still paddle at 40 m³/s (jetty about −1), although you "
             "will touch the bottom.\n\n"
             "At Midsummer 2015 the discharge was 160 m³/s and a week later 140 m³/s; there were "
             "plenty of airy blunts at both (SYKE 20.6.2015: Ruunaa 155 m³/s, 27.6.2015: 139 m³/s)."),
            ("Paddle signals",
             "In summer the Lieksanjoki has a lot of rafting company boats, so paddle signals have "
             "been agreed for Neitikoski. A craft coming from upstream (kayak, canoe, raft or wooden "
             "boat) raises its paddle or oar vertically well before the rapid. Paddlers below the "
             "rapid reply: vertical paddle = the rapid is clear, go ahead; horizontal paddle = there "
             "are paddlers in the rapid, wait. Permission usually comes in less than a minute."),
            ("Year-round spot",
             "Neitikoski stays open even in winter: national team paddlers have opened the season in "
             "January at −16 °C, and the wave was in good shape (SYKE 23.1.2011: Ruunaa 37 m³/s). In "
             "March they paddled at low water surrounded by ice (SYKE 12–20.3.2011: Ruunaa 31–32 "
             "m³/s). In winter you have to leave before you get cold, because the walk to the car "
             "park feels long when you are freezing. The Ruunaa hiking centre is right next to the "
             "rapid."),
            ("Competitions",
             "The European Freestyle Kayaking Championships were held at Neitikoski on 10–13 June "
             "2026, and the home competition brought a gold medal to Finland."),
        ),
    ),
    "Trollforsarna (Piteälven)": Kuvaus(
        "Trollforsarna (Trollforsen) is a section of rapids on the Piteälven in Swedish Lapland and "
        "a popular summer destination for Finnish whitewater paddlers – in July 2012 more than a "
        "dozen Finns sat around the same campfire. A well-signposted, 11 km gravel road leads to the "
        "rapids from the main road. You can camp for free along the shore road leading to the "
        "rapids: there are outhouses, spring water pipes and stone fireplaces (bring your own "
        "firewood). The best season is June. The Swedish Norrlandsturen event has brought dozens of "
        "paddlers here around Midsummer and July (2010, 2011).",
        (
            ("The rapids",
             "Paltvalsen is a big wave that in July 2011 was surfed for five days without a queue "
             "(SMHI 2–7.7.2011: Gransel 312–260 m³/s). It works even at high water, although at "
             "times it can be violent, and the pour-over hole below it is a horrible place ('let no "
             "amateur paddler go into it'). The next rapid has two good holes, of which the upper "
             "one is an excellent loop machine.\n\n"
             "Creeking Delta (the upper section) is a more technical section of small drops; at high "
             "water the rapids are rapids rather than rock gardens and the lines are easier. After "
             "the bridge, at the end of the section, there is a powerful hole. Further down starts "
             "the final run, where you ride the waves for at least four minutes. According to "
             "Tuus-Melojat there is one compulsory portage on the route, and an alternative line can "
             "almost always be found. An evening run downstream, with the car shuttled in advance to "
             "the combined rail and road bridge, took about three hours."),
            ("Experiences",
             "Midsummer 2010: a relaxed trip, the Creeking Delta rapids and the lines of the final "
             "drop (SMHI 25–27.6.2010: Gransel 208–200 m³/s). In July 2011 the water was high, and "
             "Paltvalsen was in good but at times violent shape (SMHI 2–7.7.2011: Gransel 312–260 "
             "m³/s). In June 2012 Paltvalsen worked really well despite the large amount of water "
             "(SMHI 16–17.6.2012: Gransel 428–421 m³/s). On the way it is worth stopping to look at "
             "Storforsen – 'for once a rapid has a name that describes it well' (it means 'the big "
             "rapid')."),
        ),
    ),
    "Taivalkoski": Kuvaus(
        "After many experiments, a rodeo hole and a neat slalom course alongside it have been built "
        "at the Taivalkoski paddling centre. It is about a two-hour drive from Oulu. The rapid is "
        "good for practising catching eddies and river running: the upper part is more demanding, "
        "the lower part easy. On the bank there is a service building with a sauna.",
        (
            ("Rodeo hole",
             "The hole halfway down the rapid got its final shape in 2002. It became a pour-over "
             "type: vertical moves are easy, but surfing and other wave moves don't really work. "
             "osm.fi describes it as a moderate, slightly one-sided and rather narrow hole that "
             "suits learning to spin in a hole. The renovated and repaired hole was praised by "
             "national team paddlers in 2013: at the right water level it was, in their words, 'the "
             "best play hole in Finland', where all moves worked on both sides. The hole was "
             "repaired again in August 2014."),
            ("Water",
             "There is a regulation dam at the top of the rapid. When the water drops, you can order "
             "more from the leisure department of the municipality of Taivalkoski. In spring there "
             "can be too much water (5/2010)."),
            ("Events",
             "At the Taivalkoski paddling festival, paddlers compete for the title of king of the "
             "rapid in three disciplines – slalom, freestyle and boatercross – in the same kayak. "
             "The rapid has also hosted slalom and boatercross competitions (2023), the European "
             "Masters Games slalom (2023) and national team training camps."),
        ),
    ),
    "Sanginjoki": Kuvaus(
        "The Sanginjoki is a good paddling river about 80 km long that flows into the Oulujoki at "
        "Madekoski, right on the edge of Oulu. The upper reaches have a wilderness feel, and there "
        "is one bigger rapid whose last part is downright tricky at low water.",
        (
            ("Rapids section",
             "The river's most rapid-filled section starts a little above Lemmenpolku and ends at "
             "Taivalkoski next to the golf course. This roughly 8 km stretch is fun at flood time. "
             "The biggest rapids are close to the Oulujoki. The river is at its best well above 10 "
             "m³/s, but it is quite runnable at least at 8 m³/s."),
        ),
    ),
    "Kuivajoki": Kuvaus(
        "The Kuivajoki is about 75 km from Oulu towards Kemi (35 km from Kemi). It is runnable for "
        "about three weeks after the ice goes out. Right after ice-out the last part of the run has "
        "big waves and play spots; a week later (Ravaska water level about 28 m) the waves are "
        "smaller and there is more dodging of rocks.",
        (
            ("Route",
             "The upper part from Oijärvi to the village of Hyry (about 25 km) is gentle current. "
             "After that comes the best part of the river, about 17 km long, with few pools. The "
             "biggest rapid, Kattilakoski, is about 4 km upstream of Asemankylä. Right after ice-out "
             "the 4 km stretch from Kattilakoski to the Asemankylä bridge is a fun play run. Another "
             "good put-in is the shooting range, from where it is about 35 km to Kuivaniemi."),
            ("Put-in",
             "From Asemankylä along the Oijärvi road about 4 km, until there is a sign 'Ravaska' on "
             "the left. Drive as far as the road goes and the river is visible."),
        ),
    ),
    "Olhavajoki": Kuvaus(
        "The Olhavajoki is a small river, 29 km long, that flows from Lake Kaihuanjärvi into the Bay "
        "of Bothnia at the village of Olhava, about 50 km from Oulu towards Kemi. The total drop is "
        "76.5 m. There is enough water for paddling for a week or two after the ice goes out; "
        "Kaihuanjärvi may still be frozen then. There is no discharge data, but the flood peak and "
        "ice-out coincide with the Kuivajoki. Because there are few lakes, the Olhavajoki drops "
        "faster than the Kuivajoki.",
        (
            ("Route",
             "The first kilometre from the lake winds with the current through willow thickets. The "
             "river mostly has small rapids, and even the pools flow nicely at flood time. "
             "First-timers should treat the two bigger rapids with respect and scout them from the "
             "bank.\n\n"
             "Sahankoski is at the Konttilantie bridge. The rapid starts in two branches: on the "
             "right a small drop, on the left an S-bend with big waves at its end. The branches join "
             "in a small pool, and under the bridge a hole almost the width of the bridge opening "
             "awaits; you punch through it at a suitable spot.\n\n"
             "The biggest rapid starts a little after the railway bridge, about a kilometre before "
             "the bridge of the Oulu–Kemi road. First you slip between two big rocks, then there is "
             "solid manoeuvring around holes. This rapid is clearly bigger than the river's other "
             "rapids."),
            ("Getting on and off",
             "The road runs close to the river in several places, so you can put in at many spots. "
             "You can take out for example at the sports field behind the Olhava school. If you want "
             "to skip the last rapid, there is a road to the shore above the railway."),
        ),
    ),
    "Simojoki": Kuvaus(
        "The Simojoki is about 85 km from Oulu towards Kemi (25 km from Kemi). At summer levels it "
        "is a good river for beginners and touring paddlers. At flood the river suits experienced "
        "paddlers only: for them the best time is a couple of weeks after ice-out. At summer levels "
        "the river is not worth it for rodeo paddlers.",
        (
            ("Alaniemi – Simo",
             "A day trip can start at the Alaniemi bridge (about 25 km from the Oulu–Kemi road "
             "towards Ranua) and end next to the sports field between the railway and road bridges. "
             "Roads run on both sides of the river up to Alaniemi. The stretch is almost all small "
             "(at flood, big) rapids or moving water, with one long pool (Karisuvanto). There are "
             "three bigger rapids (II–III) on the way. The biggest is Hamarinkoski, about 8 km up "
             "from the Kemi road."),
            ("Kalliokoski",
             "The best play spot is Kalliokoski, about 4 km downstream of Alaniemi. At high water it "
             "has a great surf wave and, a little lower down on the north bank, a hole. Kalliokoski "
             "is easy to reach from the road on the south side, from which the rapid is visible; the "
             "carry is about 100 m."),
        ),
    ),
    "Lieksanjoki (Matkalahti – Siikakoski)": Kuvaus(
        "The Lieksanjoki paddling route starts near the eastern border above Lake Ruunaanjärvi and "
        "usually ends at the Naarajoki bridge. The most commonly paddled section is Matkalahti – "
        "Siikakoski (22.5 km), especially from Neitikoski to Siikakoski. Apart from Paasikoski, all "
        "the rapids are worth scouting from the bank before running them.",
        (
            ("Route kilometre by kilometre",
             "0 km Matkalahti: boat ramps and a jetty.\n\n"
             "5 km Paasikoski (I): good/excellent passability, shallow channel. At low water the "
             "best line is right by the left or right bank. Fireplace on the right at the top, "
             "lean-to shelter on the left below.\n\n"
             "6 km Haapavitja (II): 1200 m, drop 6.1 m. The biggest waves are right below the "
             "suspension bridge in the first 400 metres; the rest is easy. The easiest line after "
             "the bridge is close to the left bank. Before the bridge there is a hole on the right "
             "that inexperienced paddlers should avoid. Scouting is necessary.\n\n"
             "9 km Neitijärvi: the route turns sharply to the right; Saunaniemi lean-to and the "
             "Huuhkajanvaara viewpoint; Neitisaari island (tent site, lean-to) can be passed on "
             "either side.\n\n"
             "15 km Neitikoski (II): 200 m, drop 1 m. Halfway down there is a big hole almost the "
             "width of the rapid that can stop and capsize an inexperienced paddler. The right side "
             "of the channel is rocky; the recommended line is on the left, and experienced paddlers "
             "can bypass the hole right by the left bank. The easiest way through the hole is at the "
             "tongue in the middle. Below: a lean-to and the Ruunaa hiking centre.\n\n"
             "17.5 km Kattilakoski (II): 150 m, drop 1.4 m. The lower part has big, sharp waves and "
             "whirlpools, and exceptionally strong eddies on both sides. The recommended line is the "
             "middle channel. The rest stops at the rapid are used by rafting companies.\n\n"
             "20 km Murrookoski (II): 300 m, drop 2.6 m – the most difficult rapid on the route. "
             "Rocky, with big waves and holes, and the last part is very rocky at low water. The "
             "recommended line is on the left.\n\n"
             "21 km Siikakoski (II): 1300 m, drop 4.6 m. At the start there are two islands joined "
             "by a rock dam, and the rapid bends sharply to the left; in the bend the main current "
             "pushes towards the island ahead on the right. The biggest waves are in the first 50 "
             "metres on the left side and can be avoided by running the right edge.\n\n"
             "22.5 km Siikakoski take-out: road to the shore, fireplace and toilet. After this a "
             "calm river section begins."),
            ("Neitikoski paddle signals",
             "In summer the Lieksanjoki has a lot of rafting company boats, so paddle signals have "
             "been agreed for Neitikoski. A craft coming from upstream (kayak, canoe, raft or wooden "
             "boat) raises its paddle or oar vertically well before the rapid. Paddlers below the "
             "rapid reply: vertical paddle = the rapid is clear, go ahead; horizontal paddle = there "
             "are paddlers in the rapid, wait. Permission usually comes in less than a minute."),
        ),
    ),
    "Liminganjoki": Kuvaus(
        "The Liminganjoki is the most surprising river of the Ostrobothnian plains. Above highway 8 "
        "it is a slow-flowing brook far from the road, but downstream of highway 8 the river drops "
        "steeply into the centre of Liminka: about 30 metres over five kilometres. The rapids are "
        "easy, class I, and the river landscape is beautiful cultural landscape of the Oulu region.",
        (
            ("Route",
             "Whitewater paddlers should put in at the highway 8 bridge. The trickiest part is "
             "finding the best line between the islands in the rapid right 150 m below the put-in. "
             "The rapids section ends after the Ala-Kestilä arboretum a little before Vanha Liminka, "
             "but the cultural landscape is worth enjoying at least as far as the Vanha Liminka "
             "museum area. A good take-out is near the sports field."),
            ("Hazards",
             "The river would be a very pleasant spring flood river were it not for the fallen "
             "trees, of which there are many. They easily block the narrow river completely, and it "
             "is not easy to paddle upstream in a brisk current – keep safe distances. After the "
             "bridge following highway 8, a couple of wire fences have been strung across the river "
             "at a paddler's neck height. The tree situation was worst downstream of the Värminkoski "
             "bridge and best between highway 8 and the Vaattanen bridge and on the last part from "
             "the arboretum to Liminka."),
            ("Water level",
             "The water situation at Liminka can be estimated from the discharge of the "
             "Tyrnävänjoki. On the autumn 2010 trip the Tyrnävänjoki discharge was 2.5 m³/s, which "
             "was too little."),
        ),
    ),
    "Muhosjoki": Kuvaus(
        "The Muhosjoki in Muhos is a river divided into three very different parts. The upper part "
        "is lively small rapids, the middle part is wild but full of fallen trees, and the Suokylä "
        "rapids section in the lower part is the most magnificent part of the river.",
        (
            ("Upper part",
             "Huikola bridge – Vääräkoski: Really nice paddling: there are no long pools, and the "
             "rapids have a good gradient. The biggest rapid is perhaps Kuurnankoski, where at low "
             "water you should take the right-hand branch. Small play spots could form at least at "
             "Kuurnankoski and Kalliokoski."),
            ("Middle part",
             "Vääräkoski – Murtokoski: The character of the river changes completely: there are no "
             "rapids, there are plenty of fallen trees, and portages are tricky because of the "
             "steep, clayey banks. Still, the stretch is very beautiful and wild – for touring "
             "paddlers in early summer once the flood has dropped, especially when the bird cherry "
             "is in bloom or in autumn colours. Whitewater paddlers should drive on to Murtokoski."),
            ("Lower part",
             "Murtokoski – Suokylä – Kajaanintie: After Murtokoski there are a couple of kilometres "
             "of small rapids in beautiful wilderness, then about 4 km of flatter water with few "
             "trees (beavers may change the situation). 1–2 km upstream of the Suokylä bridge there "
             "are nice small rapids that are a little shallow at autumn levels.\n\n"
             "From the Suokylä bridge begins the most magnificent part of the river, a rapids "
             "section of a little over a kilometre down to below Liimanninkoski, which could suit "
             "play paddlers too at spring flood. Right below the bridge is Ämmänkoski and its drop, "
             "whose line is worth checking from the bank. In spring 2010 there was a tree awkwardly "
             "in the line of the drop; in autumn it was clear. Halfway down the next rapid "
             "(Käyräkoski, right branch) there was a tree across the river in autumn 2010. Take out "
             "after the rapids section, but check the take-out in advance because of high banks and "
             "mud. After the take-out there is the Lions Club boat jetty, below which the river has "
             "been cleared. The 10-plus km to Kajaanintie is boring for whitewater paddlers; for "
             "example the Hyrkäs school works as a parking spot and take-out."),
        ),
    ),
    "Temmesjoki": Kuvaus(
        "You can paddle 70 km of the Temmesjoki if you like, but it is also excellent for opening "
        "the whitewater season for less experienced paddlers. Head for the river right after the ice "
        "goes out, usually around May Day. There are several suitable put-ins.",
        (
            ("Haurukylä – Vehkamaantie",
             "A nice afternoon run with a good flow is for example from the (demolished) Haurukylä "
             "bridge to the Vehkamaantie bridge (also 'Ylempi Ketunmaan silta'). There are several "
             "rapids, all quite easy, class I. The river landscape is traditional and beautiful "
             "cultural landscape of the Oulu region, and there is no trace on this stretch of the "
             "rubbish dumps mentioned in the old river description. The gauges used are the "
             "discharges of the Temmesjoki and the Tyrnävänjoki."),
        ),
    ),
    "Pahakurkkio (Kalixälven)": Kuvaus(
        "Pahakurkkio ('Pahis') is the canyon section of the Kalixälven at Saittarova in the "
        "municipality of Pajala, Sweden: a series of seven drops over about 3–4 km. The first drop, "
        "Åretsvågen, is a famous surf wave. The season is as long as the summer. At spring flood the "
        "canyon has big, pushy water – 'like an icy Zambezi' – and paddling then is not relaxed; a "
        "swim can be fatal. As the water drops, the play spots appear and the rapid becomes "
        "friendlier.",
        (
            ("The rapids",
             "Drops 1–3 are about class III, number four has a hole on the right, number five is the "
             "most difficult and 6–7 are class IV. At high water (above about 220 m³/s at Männikkö) "
             "the rapids are big and number five is class V. The 'death hole' of the fifth drop has "
             "haunted many a paddler's mind. The play spots have good eddies, and the lower drops "
             "are pleasantly challenging runs. The little hole is a good place to practise the "
             "McNasty, and the wave is an easy place to practise the kingfisher."),
            ("Åretsvågen and water levels",
             "Åretsvågen is sensitive to the amount of water. In June 2012 its 'famous wall' worked "
             "(SMHI 2–3.6.2012: Männikkö 212–191 m³/s), and in June 2013 it was at its best on "
             "dropping water (SMHI 6–9.6.2013: Männikkö 239–226 m³/s). In May 2013 there was too "
             "much water: Åretsvågen did not work, but there were a couple of other fun waves at the "
             "same spot, and the rapid looked completely different from low water (SMHI "
             "22–23.5.2013: Männikkö 262–266 m³/s, 27.5.2013: 311 m³/s). At autumn levels almost all "
             "hole moves worked in the hole of the first drop (SMHI 17–19.9.2010: Männikkö 77–87 "
             "m³/s). The exact Männikkö discharges on the visit days are shown in the notes for the "
             "features below."),
            ("Accommodation",
             "There are cottages with saunas for rent nearby – in autumn a much more pleasant option "
             "than a cold tent."),
        ),
    ),
    "Vikaköngäs (Raudanjoki)": Kuvaus(
        "Vikaköngäs on the Raudanjoki near Rovaniemi is a very familiar spot for Rovaniemi "
        "whitewater paddlers. It is an outdoor recreation area developed by Metsähallitus, and "
        "groynes have been shaped in the rapid to create eddies for fishing and paddling. The rapid "
        "works for training all season, from the low summer water of 15–20 m³/s to the roar of the "
        "spring floods at 300–450 m³/s. The gauge used is the inflow to Lake Olkkajärvi.",
        (
            ("Water levels",
             "The eddies work best for paddling below 50 m³/s. At 15–20 m³/s the rapid is fairly "
             "rocky, but there is always something to manoeuvre around. At summer levels the rapid "
             "is an excellent training spot, for example for slalom-style fitness paddling. At "
             "spring flood the groynes are under water, and running the rapid gives you a feel for "
             "bigger whitewater; about 300–350 m³/s is best for bigger waves. On 13 May 2010 (180 "
             "m³/s) there was not yet big water, and no real play spots either."),
            ("Competitions",
             "The Finnish boatercross championships were held at Vikaköngäs on 29 May 2011. The "
             "rapid proved to be an excellent boatercross venue, and the course built for it was "
             "praised."),
        ),
    ),
    "Korpikoski (Raudanjoki)": Kuvaus(
        "Korpikoski is a small, rocky and short rapid on the Raudanjoki that flows under the bridge "
        "of road 82 and ends in a big pool. The rapid is easy to reach from the Vikaköngäs car park: "
        "carry past the carpet-washing place to the bottom of the snowmobile trail and paddle along "
        "the pool to below the rapid.",
        (
            ("Training spot",
             "When the discharge drops below 30 m³/s, a big rock appears below the rapid that splits "
             "the current into two crisp eddy lines. The spot is especially good for whitewater "
             "courses and technique training, and you can play on the eddy lines in old-school style "
             "– 'the worse the boat, the more fun'. Korpikoski especially suits new whitewater "
             "paddlers: there is enough current to polish your technique, but a swim is like "
             "splashing at a lake shore. An easy place to get a feel for moving water and build a "
             "routine for your roll."),
        ),
    ),
    "Vaattunkiköngäs (Raudanjoki)": Kuvaus(
        "Vaattunkiköngäs is a straight and slightly narrowing stretch of rapid on the Raudanjoki "
        "near the Vaattunki hiking trail. After a shallow and rocky section the rapid bends into a "
        "pool.",
        (
            ("Training spot",
             "After the bridge, eddies form on both sides of the current that are great for paddling "
             "training. At discharges below 250 m³/s the rapid is good for practising ferrying "
             "across a firmer current in both directions. At flood levels you get a bit of a feel "
             "for paddling bigger waves."),
        ),
    ),
    "Marraskoski (Ounasjoki)": Kuvaus(
        "Marraskoski on the Ounasjoki is the traditional play spot of Rovaniemi paddlers. The rapid "
        "is short: in practice one hole on the right side of the river and a couple of eddy lines on "
        "the left. A long eddy forms in the middle that you can use for surfing and playing on the "
        "eddy lines. The rocks on the left bank are good for basking on a summer day.",
        (
            ("Summer surfing",
             "About 100–250 m³/s suits summer surfing, when the hole still has some size and the "
             "eddy is usable. Above 250 m³/s it is hard work to paddle onto the surf and you have to "
             "hurry back to the eddy, and below 100 m³/s the hole gets shallow, but you can still "
             "play on the eddy lines. According to Tuorala the wave works at about 160–250 m³/s. On "
             "9 June 2010 (88 m, about 250 m³/s) the rapid was in good shape for whitewater "
             "training: the eddy lines were strong, and the wave in the main channel worked too."),
            ("Soulwave",
             "At spring flood above 800 m³/s big surf waves form in the middle-left of the river. "
             "The wave christened Soulwave is best caught by dropping in from the left bank, and you "
             "exit the surf to the same side. For repeat surfs you carry along the shore path, but "
             "from near the waves you can also paddle well upstream using the eddy. On 21 May 2010 "
             "(90 m, 1040 m³/s) there was a great surf wave in the middle of the river where you "
             "could surf for an hour: on the left a green shoulder for clean spins, in the middle a "
             "less breaking tongue and on the right a powerful foam pile for hole moves. On the east "
             "side of the river there was also a smaller surf wave that you could reach from the "
             "eddy."),
        ),
    ),
    "Molkoköngäs (Ounasjoki)": Kuvaus(
        "Molkoköngäs is on the Ounasjoki between Rovaniemi and Kittilä: a short and rather narrow "
        "stretch of rapid in the middle of a beautiful, canyon-like shore formation. It is usually "
        "paddled in a play-paddling spirit.",
        (
            ("Molkoaalto",
             "At discharges below 300 m³/s (Kaukonen), a train of a couple of surf waves forms on "
             "the left edge of the rapid next to the rocks, near the viewpoint. According to Tuorala "
             "it works at about 220–280 m³/s and is at its best at about 260–270 m³/s. The spot "
             "works best with short freestyle kayaks, but at lower levels there is also something to "
             "ferry on for a longer whitewater kayak. Surfing requires a quick surf–carry–surf "
             "rhythm, but with crisp paddling you can catch the eddy between the wave train and the "
             "rocks.\n\n"
             "In May 2014, according to national team paddlers, Molkoaalto was easy to paddle and "
             "had enough speed. You have to hurry to the eddy, but you almost always make it. The "
             "wave is not very big, but it suits the start of the season, and a couple of the lower "
             "waves are good for blunts too. As the water rises the wave turns green and the moves "
             "get harder."),
        ),
    ),
    "Kutujoki": Kuvaus(
        "The Kutujoki flows from Lake Otermajärvi into the Oulujoki north of Vaala. It is the "
        "longest and most rapid-filled part of the 50 km Tervajoki–Kutujoki paddling route: about 17 "
        "km and 15 rapids. The Kutujoki has the route's only class II rapids – Myllykoski right at "
        "the start, and Monisaarikoski and the 1400 m long Petäjäkoski halfway down the river. The "
        "other rapids are class I. The river suits beginners and touring paddlers, and it is at its "
        "best in early summer.",
        (
            ("Route and services",
             "At the outlet of the river (the top of the Kutujoki) there is a suspension bridge and "
             "an open wilderness hut, and along the river there are rest stops with fire rings and "
             "maintenance; Monisaari has a lean-to. The liveliest part is at the fish farm. The "
             "route ends at Järvikylä by highway 22 between Oulu and Kajaani, about 87 km from Oulu.\n\n"
             "At flood time an open canoe may take on the odd wave, but for a kayaker who has been "
             "in rapids before the Kutujoki is easy. The river is also known for recreational "
             "fishing: catchable-size brown trout and rainbow trout are stocked in it."),
        ),
    ),
    "Tervajoki (Vaala)": Kuvaus(
        "The Tervajoki is the upper course of the Kutujoki and the upper part of the "
        "Tervajoki–Kutujoki paddling route. It is about 14 km from Lake Pienanjärvi to Lake "
        "Otermanjärvi. The whole route is 50 km long, with 25 rapids and a 40-metre drop. The route "
        "consists of a few lakes and the long river sections connecting them. The lakes have a "
        "couple of open stretches, but otherwise the scenery is small-scale, and the river meanders "
        "through northern Finnish forest. The route is at its best in early summer.",
        (
            ("Rapids and services",
             "The Tervajoki rapids are class I (among others Vääräkoski, Pirunkoski, Pystönkoski and "
             "Holtto) – according to osm.fi 'a good little river, no surprise rapids'. There is an "
             "open wilderness hut at Pirunkoski by the river. From Joensuunperä it is about 115 km "
             "back to Oulu.\n\n"
             "The Tervajoki has no gauging station of its own. That is why the app uses the inflow "
             "to Lake Otermanjärvi as the gauge, of which the Tervajoki is the main source."),
        ),
    ),
    "Kuusinkijoki": Kuvaus(
        "The Kuusinkijoki is a flood river east of Kuusamo, less well known than the Kitkajoki. It "
        "has many lively rapid sections (I–II+) and few pools: a drop of about 100 m over 15 km and "
        "almost 20 rapids of varying difficulty with big waves, holes and small drops. The river has "
        "been one of the most popular whitewater racing venues in Finland. Because it is so rocky, "
        "it is recommended only at high water and in a plastic kayak. There are rugged cliffs along "
        "the river.",
        (
            ("Safety",
             "In spring the water is extremely cold and the rapids are fairly long, partly between "
             "steep rocky banks, so a dry suit is necessary. A swim in a long rapid can turn into a "
             "long one."),
            ("Rapids from top to bottom",
             "0.0 km put-in in the channel below the Myllykoski power plant. 0.8 km Käpykoski (about "
             "5 km, with a pool in between). 4.9 km Melalampi (scout from the right).\n\n"
             "5.3 km Kiukaankorvankoski (II+, 0.9 km): at the first rocks a hole on the right, below "
             "the lower rock a 'cauldron'. Rocky; the line is mostly down the middle. 6.8 km a wider "
             "section. 7.1 km Rojokoski and five other class I rapids.\n\n"
             "12.4 km Hanhisuvanto (narrow, steep banks). 12.6 km Hanhivirta (II+, 0.2 km): line "
             "down the middle; 300 m further down a big hole-wave, then the rapid bends to the left "
             "and drops in small ledges into the Paljakka pond (lean-to on the left).\n\n"
             "13.1 km Paljakka 1 (II+, 0.8 km): a drop of about a metre at the start, holes at the "
             "edges, line down the middle. It continues as big waves curving to the left; in the "
             "lower part, at the right-hand rock, two parallel holes. 13.9 km Takkupyörre (regroup; "
             "lean-to on the right).\n\n"
             "14.1 km Paljakankoski 2 (0.8 km): a steadily strengthening rapid turning to the right, "
             "with big-rock waves and holes; the lower part is wide and rocky. 14.8 km Lohipyörre "
             "(small pool, lean-to on the right, possible take-out).\n\n"
             "14.9 km Raatekoski (II, 0.6 km): a fast straight rapid with a small drop at the "
             "bottom; line first down the middle, then along the left edge. The river widens and "
             "continues as an even rapid to Koivumutka: 16.8 km Koivumutkat 1, 17.4 km Koivumutkat "
             "2, 17.6 km a wide section, pool on the left."),
            ("Water levels",
             "The gauge is SYKE's calculated discharge for Myllykoski (the station has no measured "
             "observations). On 25 May 2024 the discharge was about 50 m³/s: big waves, and at times "
             "you had to paddle hard to avoid getting stuck in consecutive big waves and holes. The "
             "paddle took 2 h 30 min (12 km). On 18 May 2025 the discharge was 28 m³/s and the river "
             "completely different: the rapids were shallow and the rocks close to or above the "
             "surface. Hanhivirta and the Paljakka rapids still had relatively big waves, although "
             "the paddle hit rocks at the bottom of the holes. In the Retkipaikka blog the route (16 "
             "km) was paddled by packraft on 26 June 2020 at a discharge of 23 m³/s: the rapids were "
             "slower at the start and faster towards the end, 4–5 h of paddling. According to the "
             "blog the river is not for beginners but requires whitewater and rescue skills."),
            ("Other",
             "According to the Metsähallitus brochure the Kuusinkijoki paddling route is 17.5 km. "
             "The Pieni Karhunkierros (Little Bear's Ring) hiking trail in Oulanka National Park is "
             "nearby. Piirainen's paddling diary has its own route page for the river (Other "
             "routes). According to Retkipaikka the route ends close to the Russian border, so don't "
             "run the river too far: you can recognise the take-out by a shallow rapid and a bend "
             "with a big sandbank. The Kuusamon Koskimelojat route description gives a length of "
             "17.7 km and a grade of I–II+."),
        ),
    ),
    "Savinajoki": Kuvaus(
        "The Savinajoki is a flood river flowing from Salla into Kuusamo, of the same type as the "
        "Kuusinkijoki but wider and with different waves. After Lake Viiksjärvi the river drops "
        "through beautiful canyon scenery as an almost continuous class I–II rapid all the way to "
        "Savilampi, a drop of 60 m over a little more than 10 km. Before the rapids there is a lake "
        "section of about 3 km. In summer the river is low and rocky.",
        (
            ("Safety",
             "In spring the water is extremely cold and the rapids are long, so a dry suit is "
             "necessary."),
            ("Water levels",
             "The Savinajoki has no SYKE station of its own; the gauge is the discharge of the "
             "Oulankajoki downstream, which indicates the stage of the spring flood. On 26 May 2024 "
             "(Oulankajoki 99 m³/s) the route was paddled from Niitselyksentie to Savilampi: 15.5 "
             "km, 3 h. On 18 May 2025 (Oulankajoki 135 m³/s) the Savinajoki had considerably more "
             "water than in 2024, apparently because the lake upstream thawed later. According to "
             "Piirainen the river's many rapids have enough water to run in early summer. In the "
             "Retkipaikka blog the river was paddled by packraft on 24 June 2020, when the "
             "Oulankajoki had only 24 m³/s: the rapids were easy class I and the route suited even "
             "beginners. In a kayak such low water is shallow and rocky."),
            ("Other",
             "According to the Metsähallitus brochure the Savinajoki paddling route is 14 km. A "
             "possibly surfable small wave has been found on the Oulankajoki above Kiutaköngäs. "
             "Running Kiutaköngäs is life-threatening, and Taivalköngäs is portaged on foot. The "
             "Retkipaikka route combined hiking and paddling: a 6 km walk from the Hautajärvi nature "
             "centre along the Karhunkierros trail to the Perttumakoski lean-to, 10 km of paddling "
             "to Savilampi and a 1 km walk to the Kanjonin kurkkaus car park. The Kuusamon "
             "Koskimelojat route description gives a length of 13 km and a grade of I–II."),
        ),
    ),
    "Siiponjoki (Kalajoki)": Kuvaus(
        "The Siiponjoki is a small, mostly natural river south of Kalajoki, about 40 km long. The "
        "river has rapids, fallen trees and sand banks. It meanders, changing its course, and at low "
        "water you may have to carry or line your kayak on shallow sections; there are also tricky "
        "spots because of rocks. There is apparently only one built rest stop, the Pleuna lean-to.",
        (
            ("Difficulty",
             "Moderately demanding: the rapids can be avoided, but the route may otherwise prove "
             "hard going, and you have to get out several times. This is not an easy and smooth "
             "route – bring a brisk outdoor attitude and a dash of adventurous spirit."),
            ("Equipment",
             "A whitewater kayak or a river touring kayak (or a plastic sea kayak). Fit your "
             "day-trip supplies (food, change of clothes) into the kayak. Wear a paddling helmet."),
            ("Surroundings",
             "The Siiponjoki nature trail, about 20 km long, runs along the river through pine "
             "forests; there is a kota hut and two lean-tos on the riverbank (Visit Finland). Near "
             "the Pleuna lean-to grows the oldest tree in the area, the 'ancient pine'."),
            ("Water situation",
             "The Siiponjoki has no SYKE forecast station (Kurikkala only has an observation station "
             "without a forecast), so the app does not score the river. At low water there are more "
             "portages."),
        ),
    ),
    "Oulujoki": Kuvaus(
        "The Oulujoki is the outflow of Lake Oulujärvi and flows into the Bay of Bothnia in Oulu. It "
        "is the main river of Northern Ostrobothnia and Kainuu, and most of Kainuu belongs to its "
        "catchment. The river is regulated and always paddleable. The scenery from Oulujärvi to Oulu "
        "is good, and as you pass the power plants you can wonder what the river was like before it "
        "was built.",
        (
            ("Paddling options",
             "The rapids of the Oulujoki have been harnessed for power plants, so the river is for "
             "touring and fitness paddling. Rapids can be found on the tributaries Sanginjoki and "
             "Muhosjoki (see their own pages)."),
        ),
    ),
    "Oulun edustan saaret": Kuvaus(
        "Off Oulu there are easily accessible sea kayaking destinations, from the nearby islands to "
        "a circumnavigation of Hailuoto. Conditions depend on the wind, and there is no gauge chart. "
        "The osm.fi description also includes trips further afield: to the Rahja archipelago, to the "
        "islands of the northern Bay of Bothnia on the Finnish and Swedish sides, and to the "
        "Kokkola–Vaasa archipelago.",
        (
            ("Off Oulu",
             "Hermannit: the nearest destination, three islands about 2.5 km west of the mouth of "
             "the Toppila canal; the west shore of the middle island has a nice sandy beach. "
             "Laitakari: about 10 km from the mouth of the Toppila canal, with a wooden lighthouse "
             "as a landmark. Kropsu: about 1.5 km west of Virpiniemi, a wooded island and a good "
             "mushroom spot. The island has a jetty and fireplaces and is a favourite of boaters, so "
             "it is not the place to look for peace and quiet. Santapankki: a sandbank about 16 km "
             "west of Martinniemi."),
            ("Hailuoto",
             "A circumnavigation of Hailuoto is over 100 km, depending on how closely you follow the "
             "bays. The island has small open wilderness huts that work as bases for paddlers: on "
             "the Vaski shore, on the Ulkokarvo shore and at Sunijärvi 1.4 km inland from the "
             "Keskikarvo lighthouse. A big lean-to is at Hannuksenlampi about 1 km inland from "
             "Hannuksennokka. Marjaniemi has a campsite, and the Huikku ferry landing has a café. "
             "The duck hunting season begins at the end of August: don't paddle in the shoreline "
             "reeds then."),
            ("Further afield",
             "Rahja south of Kalajoki is a small area of many islands and skerries that you can tour "
             "in a weekend. There are lean-tos, fireplaces and two open wilderness huts, of which "
             "the Koivukari hut is on the island of Ryöppä. You cannot paddle through between Ryöppä "
             "and Pappilankari.\n\n"
             "The northern Bay of Bothnia (Haparanda–Kalix–Luleå and Bothnian Bay National Park) has "
             "more and rockier islands with sandy beaches. Examples: Selkä-Sarvi (open sauna, "
             "wilderness hut), Haparanda Sandskär (Kumpula fishing village, wilderness hut, sauna), "
             "Likskär (stone labyrinths), Berghamn (boulder caves), Renskär (open sauna), Stora "
             "Huvön (the finest island in the area, a sandbank and a rock face), Lill Furuön and "
             "Rövarn. Landing restrictions in bird sanctuaries are in force from the beginning of "
             "May to the end of July. Launch sites include the Tromsöviken campsite on Seskarö, the "
             "Storön and Rörbäck swimming beaches and the Hertsöskatan marina.\n\n"
             "In the Kokkola–Vaasa archipelago (starting for example from the Brunnilandet marina), "
             "destinations include Tankar, Orsskär, Punakarit, Mikkelinsaaret and Boskäret."),
        ),
    ),
}

LAHTO_LOPPU: dict[str, tuple[tuple[str, str], ...]] = {
    "Sanginjoki": (
        ("Put-in",
         "The rapids section starts a little above Lemmenpolku on the upper Sanginjoki (osm.fi)."),
        ("Take-out",
         "Taivalkoski next to the Sankivaara golf course at Madekoski in Oulu, where the Sanginjoki "
         "flows into the Oulujoki. Drive to the golf course along Mikonmäentie."),
    ),
    "Kuivajoki": (
        ("Put-in",
         "Ravaska: from Kuivajoki Asemankylä along the Oijärvi road about 4 km, until there is a "
         "sign 'Ravaska' on the left; drive as far as the road goes and the river is visible "
         "(osm.fi). A longer trip starts from Hyry by Kuivajoentie."),
        ("Alternative",
         "The shooting range, from where it is about 35 km to Kuivaniemi (osm.fi)."),
        ("Take-out",
         "The play run ends at the Asemankylä bridge; the whole 17 km rapids section ends at "
         "Kuivaniemi (by the Oulu–Kemi road)."),
    ),
    "Olhavajoki": (
        ("Put-in",
         "Lake Kaihuanjärvi, in Kuivaniemi, Ii. From the lake the river winds through willow "
         "thickets for the first kilometre; the road runs close to the river in several places, so "
         "you can put in at many spots (osm.fi)."),
        ("Alternative",
         "Sahankoski at the Konttilantie bridge."),
        ("Take-out",
         "The sports field behind the Olhava school by the Oulu–Kemi road (highway 4), about 50 km "
         "from Oulu. You can skip the last rapid by taking out above the railway, where a road comes "
         "to the shore (osm.fi)."),
    ),
    "Simojoki": (
        ("Put-in",
         "The Alaniemi bridge about 25 km from the Oulu–Kemi road towards Ranua; roads run on both "
         "sides of the river up to Alaniemi (osm.fi)."),
        ("Alternative",
         "Kalliokoski about 4 km downstream of Alaniemi: about 100 m carry from the south side road."),
        ("Take-out",
         "The Simo sports field between the railway and road bridges (osm.fi)."),
    ),
    "Lieksanjoki (Matkalahti – Siikakoski)": (
        ("Put-in",
         "Matkalahti above Lake Ruunaanjärvi: boat ramps and a jetty at the end of Matkalahdentie "
         "(osm.fi)."),
        ("Alternative",
         "Neitikoski and the Ruunaa hiking centre (lean-to below the rapid). The Ruunaa nature "
         "centre is at Naarajoki, 13 km from Pankakoski (luontoon.fi)."),
        ("Take-out",
         "Siikakoski take-out: road to the shore (Siikakoskentie), fireplace and toilet. The longest "
         "route continues to the Naarajoki bridge (about 30 km from Matkalahti)."),
    ),
    "Liminganjoki": (
        ("Put-in",
         "The highway 8 bridge in Liminka; the rapids section starts right at the bridge (osm.fi)."),
        ("Take-out",
         "The rapids section ends after the Ala-Kestilä arboretum; it is best to take out at the "
         "Vanha Liminka museum area near the sports field."),
    ),
    "Muhosjoki": (
        ("Put-in",
         "Upper part: the Huikola bridge. Lower part: the Murtokoski put-in, followed by a couple of "
         "kilometres of small rapids (osm.fi)."),
        ("Alternative",
         "The Suokylä bridge: the river's most magnificent rapids section of a little over a "
         "kilometre starts at the bridge (Ämmänkoski right below the bridge – check the drop from "
         "the bank)."),
        ("Take-out",
         "The upper part ends at Vääräkoski; on the lower part take out right after the rapids "
         "section (near the Lions Club boat jetty) or at the Hyrkäs school. Check the take-out in "
         "advance: the banks are high and muddy (osm.fi)."),
    ),
    "Temmesjoki": (
        ("Put-in",
         "The (demolished) Haurukylä bridge in Tyrnävä, by Haurukyläntie (osm.fi)."),
        ("Take-out",
         "The Vehkamaantie bridge ('Ylempi Ketunmaan silta') in Liminka."),
    ),
    "Pahakurkkio (Kalixälven)": (
        ("Put-in",
         "The Saarikoski cabin above the rapid is the put-in for Pahakurkkio (Tuorala 2010). "
         "Pahakurkkio is outside the village of Saittarova in the western part of the municipality "
         "of Pajala; there is parking near the canyon, and Saittarova Intresseförening rents out "
         "cabins and campsites. There is no mobile phone coverage everywhere in the area "
         "(Naturkartan)."),
        ("Take-out",
         "Below the seventh drop there is a sandy beach (Naturkartan); check a suitable take-out in "
         "advance."),
    ),
    "Kutujoki": (
        ("Put-in",
         "The outlet of Lake Otermajärvi at the top of the Kutujoki: suspension bridge and open "
         "wilderness hut (osm.fi, Visit Vaala). The Kutujoki is usually approached from the west "
         "bank: a forest road leading to the upper reaches via Petäjäkoski branches off the "
         "Kajaani–Oulu road (highway 22) about 200 m west of the Autiokoski bridge (Kalalla "
         "Kainuussa)."),
        ("Take-out",
         "Järvikylä by highway 22 between Oulu and Kajaani (swimming beach); about 87 km to Oulu."),
    ),
    "Tervajoki (Vaala)": (
        ("Put-in",
         "The outlet of Lake Pienanjärvi by Vääräkoskentie in Vaala."),
        ("Take-out",
         "Lake Otermanjärvi (Joensuunperä); if you like, the route continues down the Kutujoki to "
         "Järvikylä."),
    ),
    "Kuusinkijoki": (
        ("Put-in",
         "The channel below the Myllykoski power plant in the village of Vuotunki (km 0 of the "
         "route)."),
        ("Alternative",
         "A sand pit on the left side of the road about 3.2 km from the Suorajärvi road junction. "
         "The car shuttle from the sand pit to the Koivumutka take-out is about 28 km (40 min)."),
        ("Take-out",
         "Koivumutkat: the left side of the pool after the second Koivumutka or the site of the "
         "former campsite (Koivumutkat lean-to). The last part of Saunavaarantie was in poor "
         "condition in 2025, and the cars were left about 2 km from the shore."),
        ("Alternative",
         "Lohipyörre after Paljakankoski (lean-to on the right): a steep climb and a fairly long "
         "carry of the kayaks through pine forest to the cars. The car shuttle from the lower put-in "
         "to here is only about 9 km, but part of the road is in very poor condition."),
    ),
    "Savinajoki": (
        ("Put-in",
         "Along Niitselyksentie on the Salla side, from the bridge before Pitkäkoski (the point is "
         "on Niitselyksentie; check the bridge on the map). Before the rapids, a lake section of "
         "about 3 km."),
        ("Take-out",
         "Savilampi (open wilderness hut). The kayaks are carried about 1 km to the Savilampi car "
         "park (about 40 min): a steep climb at first, then open pine forest and heather – a strap "
         "for dragging is good to have."),
        ("Parking",
         "The Savilampi car park."),
    ),
    "Siiponjoki (Kalajoki)": (
        ("Put-in",
         "The Siiponjoki nature trail car park, Pleunantie 379, Kalajoki. The gear is carried a good "
         "400 m to the shore near the Pleuna lean-to; you can have a snack break at the lean-to "
         "before paddling."),
        ("Take-out",
         "The Siiponkylä bridge: the trip is about 7 km long."),
        ("Alternative",
         "Konikarvo harbour and paddling jetty, Konikarvontie 204 (Rahja). At the end you paddle a "
         "short but fairly sheltered sea section along the shore to the harbour: a total length of "
         "just under 15 km (7 km to the Siiponkylä bridge + 7.4 km from the bridge to Konikarvo)."),
    ),
    "Oulujoki": (
        ("Put-in and take-out",
         "osm.fi does not define a fixed put-in or take-out for the Oulujoki: the river is regulated "
         "and always paddleable, and the power plants are portaged. The rapids are on the "
         "tributaries (Sanginjoki, Muhosjoki)."),
    ),
    "Oulun edustan saaret": (
        ("Put-in",
         "The mouth of the Toppila canal: about 2.5 km west to Hermannit (osm.fi)."),
        ("Put-in",
         "Virpiniemi: about 1.5 km west to the island of Kropsu."),
        ("Put-in",
         "Martinniemi: about 16 km west to the Santapankki sandbank."),
        ("Put-in",
         "Riutunkari (the Hailuoto ferry): the Hailuoto circuit is over 100 km; open wilderness huts "
         "at Vaski, Ulkokarvo and Sunijärvi."),
        ("Take-out",
         "Island trips return to the starting point."),
    ),
}

HUOMIOT: dict[str, tuple[str, ...]] = {
    "Kipinä (Iijoki)": (
        "the best play spot; above 107.85 m a surfable wave section on the outer edge (Pilari "
        "107.65–108.20 m)",
        "slow surf wave, no eddy (carry 2–20 m); Sillanalus 108.25–108.60 m, 108.59 m at the top of "
        "the optimum",
        "at its best 106.7–107.2 m; also suits whitewater SUP; fast kayak: half/full slice, "
        "something like a Jackson Fun, or a slalom boat – a modern freestyle boat is slow",
    ),
    "Koiteli (Kiiminkijoki)": (
        "at its best at 10.7 m; cartwheels, loops; at 10.37–10.45 m not much grip",
        "from 10.4 m up cartwheels and loops work; 10.37 m quite good",
        "good at about 11.0 m and below; at 10.5 m you hit rocks at the edges",
        "in the middle of the rapid at about 10.5 m",
        "at its best at 10.7 m; suits beginners",
    ),
    "Matkakoski (Tornionjoki)": (
        "below 28 m you can paddle back to the play spots",
        "27.90 m good but narrow, at the lower limit; 28.07 m wide",
        "drop in from above, carry back",
        "experienced paddlers only; the rock in the middle of the rapid is covered",
        "the Swedish wave weakens at low water",
    ),
    "Kattilakoski (Tornionjoki)": (
        "second wave 78.35–78.50 m",
        "at its best at 78.35 m; at 78.50 m it already crashes to the bottom (Tuorala)",
        "at its best at about 78.25 m, 'extremely underrated' (Tuorala)",
        "at its best at 79.00 m",
        "at its best at 78.85 m; works 78.85–79.15 m",
        "works at about 78.25 m",
        "about 79 m",
        "the more water the better",
        "needs a lot of water, the best surfs above 3000 m³/s; best 80.0–80.8 m",
        "14 km upstream; suits all levels",
        "working water level 78.00–82.00 m",
    ),
    "Kukkolankoski (Tornionjoki)": (
        "experience at 28–28.7 m; 29.2 m is too much; short eddies",
    ),
    "Vuentokoski (Tornionjoki)": (
        "28.7 m nice play spots; 28.2 m hardly worth it; above 2000 m³/s (about 31 m) 'one of the "
        "best big-water runs' (Tuorala 2010)",
    ),
    "Hawa'Ii (Iijoki, Maalismaa)": (
        "about 600 m³/s the bow hits the bottom; 850 m³/s really good and getting better; works "
        "650–1300 m³/s, 645 m³/s shallow",
    ),
    "Pyhäjoki": (
        "eddy on river right; paddle back; works 45–90 m³/s",
        "at its best at about 140 m³/s; 170 m³/s too much",
    ),
    "Siikajoki (Pöyryn pato)": (
        "excellent eddy, suits less experienced paddlers too",
        "150 m³/s: a hole with depth for loops",
        "70 m³/s: the bow hits the bottom in stern squirts; nice eddy lines; good above 100 m³/s",
        "you have to carry to the wave",
        "working water level 19.50–21.00 m NN; 19.57 m shallow, 19.75–19.79 m good",
    ),
    "Niskakoski (Lestijoki)": (
        "good eddies on both sides",
        "tricky eddy lines at high water",
    ),
    "Neitikoski (Lieksanjoki)": (
        "above 120 m³/s (jetty about 9.5) a steeper wave, wave moves are easier; you can still "
        "paddle at 40 m³/s (jetty about −1)",
        "above 110 m³/s (bridge gauge about 8) wave-like but breaks to the bottom; wave moves need "
        "explosive paddling, excellent for practising loops",
        "below 100 m³/s a hole by the forest edge, a tongue in the middle; at low water the bow or "
        "paddle hits the bottom",
    ),
    "Trollforsarna (Piteälven)": (
        "at its best at 190–240 m³/s, works from about 170",
        "works at about 220–400+, at its best at about 340; the upper limit is not known; at the "
        "lower end of Benbrytarforsen, a smooth wave, suits left-hand blunts",
        "above 300 m³/s hairy; Forsguiden: Björnidedeltat works best at lower water",
        "the same levels as the upper section, but easier",
        "always good, better above 300 m³/s",
        "good below 130 m³/s, at most about 150; Forsguiden: IV–VI, very swirly eddies, a big "
        "sucking hole",
    ),
    "Sanginjoki": (
        "at least 8 m³/s (osm.fi), works above 6 m³/s; at its best well above 10 m³/s",
    ),
    "Kuivajoki": (
        "about 28 m: smaller waves and dodging rocks; good above 28.0 m",
        "right after ice-out, big waves",
    ),
    "Olhavajoki": (
        "estimated from the Kuivajoki gauge",
    ),
    "Simojoki": (
        "suits beginners and touring paddlers",
        "experienced paddlers only; best a couple of weeks after ice-out",
    ),
    "Lieksanjoki (Matkalahti – Siikakoski)": (
        "paddle signal rules at Neitikoski",
    ),
    "Liminganjoki": (
        "2.5 m³/s at Tyrnävä was too little; watch out for trees and wire fences",
    ),
    "Muhosjoki": (
        "a little shallow at autumn levels (Tyrnävä ~3.3 m³/s)",
        "at spring flood; check the Ämmänkoski drop",
    ),
    "Temmesjoki": (
        "a spring flood river",
    ),
    "Pahakurkkio (Kalixälven)": (
        "Männikkö 191 m³/s optimal and 212 a little over (6/2012), 226–235 at its best (6/2013), 218 "
        "good (7/2010); best on dropping water",
        "77–87 m³/s autumn level easier (9/2010), 96 'almost optimal' (8/2010), 191 good and not "
        "chaotic (6/2012); at 218 number five is class V",
        "at 77–87 m³/s almost all hole moves worked, the wave at its best at the lowest level "
        "(9/2010)",
    ),
    "Vikaköngäs (Raudanjoki)": (
        "the eddies work best below 50 m³/s; 15–20 m³/s fairly rocky, but always something to "
        "manoeuvre around",
        "at flood the groynes are under water; 300–350 m³/s best for bigger waves; Tuorala 2010: 290 "
        "m³/s big waves but nothing surfable, 180 'not really anything'",
    ),
    "Korpikoski (Raudanjoki)": (
        "below 30 m³/s a big rock appears below the rapid that splits the flow into two crisp eddy "
        "lines; swims are safe",
    ),
    "Vaattunkiköngäs (Raudanjoki)": (
        "below 250 m³/s good for practising crossing a firmer current; below 50 m³/s no longer good",
        "at flood levels a bit of a feel for paddling bigger waves; Tuorala 2010: 290 m³/s a "
        "nice-looking wave train, not surfable",
    ),
    "Marraskoski (Ounasjoki)": (
        "100–250 m³/s the hole has some size and the eddy is usable, the wave best at 160–250 "
        "(Tuorala); above 250 hard work to get back; below 100 the hole is shallow",
        "Roimeloo: above 800 m³/s big surf waves in the middle-left; Tuorala: a wide wave above 1000 "
        "m³/s; drop in from the left bank",
    ),
    "Molkoköngäs (Ounasjoki)": (
        "works at about 220–280 m³/s, at its best at 260–270 (Tuorala 2012); surf-carry-surf",
    ),
    "Kutujoki": (
        "a narrow (5–10 m) river: below about 4 m³/s (summer low water) rocky; at flood an open "
        "canoe may take on a wave (osm.fi)",
        "Myllykoski right at the start, Petäjäkoski 1,400 m; rocky at low water, lively for a "
        "beginner above MHQ (18 m³/s)",
    ),
    "Tervajoki (Vaala)": (
        "a small river: rocky at summer low water (inflow 1–2 m³/s); early summer is best "
        "(municipality of Vaala); class I rapids",
    ),
    "Kuusinkijoki": (
        "25.5.2024 about 50 m³/s: big waves and holes, at times you had to paddle to avoid getting "
        "stuck; 18.5.2025 28 m³/s: shallow rapids, rocks at the surface, the paddle hit the bottom "
        "in holes – Hanhivirta and the Paljakka rapids still had big waves; 26.6.2020 23 m³/s: "
        "paddled by packraft, lively (Retkipaikka)",
    ),
    "Savinajoki": (
        "Oulankajoki 26.5.2024 99 m³/s: paddled, good; 18.5.2025 135 m³/s: clearly more water in the "
        "Savinajoki (the lake upstream thawed later); 24.6.2020 24 m³/s: paddled by packraft, easy "
        "class I (Retkipaikka) – shallow and rocky in a kayak",
    ),
}
