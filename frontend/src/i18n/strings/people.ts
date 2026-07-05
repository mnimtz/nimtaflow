export const people = {
  de: {
    // Header / list
    'people.title': 'Personen',
    'people.subtitleNamedUnknown': '{named} benannt · {unknown} unbekannt',
    'people.cropsProgress': ' · Crops {cached}/{total}',
    'people.sortTitle': 'Personen sortieren',
    'people.sortMostPhotos': 'Meiste Bilder',
    'people.sortLeastPhotos': 'Wenigste Bilder',
    'people.sortMostFaces': 'Meiste Gesichter',
    'people.sortName': 'Name (A–Z)',
    'people.sortRecent': 'Zuletzt hinzugefügt',
    'people.quickNameTitle': 'Unbenannte Gruppen schnell durchbenennen',
    'people.quickName': 'Schnell benennen',
    'people.done': 'Fertig',
    'people.selectMergeTitle': 'Mehrere Personen auswählen, um sie zusammenzuführen oder zu verbergen',
    'people.selectMerge': 'Auswählen / Zusammenführen',
    'people.select': 'Auswählen',
    'people.hideHiddenTitle': 'Verborgene ausblenden',
    'people.showHiddenTitle': 'Verborgene anzeigen',
    'people.hidden': 'Verborgene',
    'people.clusterTitle': 'Unzugeordnete Gesichter automatisch gruppieren',
    'people.clustering': 'Clustere…',
    'people.cluster': 'Clustern',
    'people.detectFacesTitle': 'Gesichter lokal auf dem Server erkennen (parallel zu den Beschreibungen) — schneller fertig, unabhängig vom KI-Backlog',
    'people.starting': 'Starte…',
    'people.detectFaces': 'Gesichter erkennen',
    'people.warmCropsTitle': 'Alle Gesichts-Vorschaubilder (Crops) vorab erzeugen — danach lädt die Personen-Seite sofort, ohne pro Video-Gesicht ffmpeg zu starten',
    'people.warmCrops': 'Crops vorbereiten',
    'people.writeFacesTitle': 'Alle erkannten Gesichter (Koordinaten + Namen) dauerhaft in die Bilddateien schreiben (MWG-Regionen) — erspart später erneute Gesichtserkennung',
    'people.writing': 'Schreibe…',
    'people.writeFaces': 'Gesichter schreiben',
    'people.add': 'Hinzufügen',

    // Select-mode banner
    'people.selectBanner': 'Wähle Personen aus (antippen). Mit 2 oder mehr kannst du sie unten zusammenführen oder verbergen.',

    // Help details
    'people.helpSummary': 'Was machen die Aktionen oben?',
    'people.helpSummaryNote': '(läuft alles auch automatisch)',
    'people.helpDetect': 'Gesichter erkennen & Clustern: laufen automatisch im Hintergrund (Erkennung laufend, Gruppierung nachts). Die Buttons stoßen es nur sofort an — musst du normal nicht drücken.',
    'people.helpQuickName': 'Schnell benennen: unbekannte Gruppen zügig durchbenennen. Tippst du einen bereits bekannten Namen, wird die Gruppe mit dieser Person zusammengeführt statt doppelt angelegt.',
    'people.helpWarmCrops': 'Crops vorbereiten: erzeugt die Gesichts-Vorschaubilder vorab (Seite lädt dann schneller). Optional.',
    'people.helpWriteFaces': 'Gesichter schreiben: speichert Namen dauerhaft in die Bilddateien (für Re-Import). Optional.',

    // Loading / empty
    'people.loading': 'Lade…',

    // Tabs
    'people.tabPeople': 'Personen ({count})',
    'people.tabUnknown': 'Unbekannte ({count})',
    'people.tabSuggestions': 'Vorschläge',
    'people.tabSuggestionsCount': 'Vorschläge ({count})',
    'people.tabUnknownFaces': 'Unbekannte Gesichter',
    'people.tabUnknownFacesCount': 'Unbekannte Gesichter ({count})',
    'people.tabHidden': 'Verborgen',

    // Suggestions
    'people.noOpenSuggestions': 'Keine offenen Vorschläge. Neue entstehen automatisch (oder „Neu berechnen" in der Pipeline).',
    'people.suggestionsHeading': 'Vorschläge — „Ist das …?"',
    'people.suggestionsHint': 'Unsichere Treffer, die ArcFace nicht automatisch zuordnet. ✓ übernehmen · ✗ verwerfen.',
    'people.recalculating': 'Berechne…',
    'people.recalculate': 'Neu berechnen',
    'people.confirmAll': 'Alle bestätigen',
    'people.rejectAll': 'Alle ablehnen',
    'people.rejectGroupConfirmTitle': 'Alle {count} Vorschläge für „{name}" ablehnen?',
    'people.rejectGroupConfirmMessage': 'Die Gesichter werden nicht zugeordnet (nur der Vorschlag entfernt).',
    'people.adopt': 'Übernehmen',
    'people.discard': 'Verwerfen',

    // Sections
    'people.namedPeople': 'Benannte Personen',
    'people.unknownPeople': 'Unbekannte Personen',
    'people.unknownPeopleHint': 'Klicke eine Person an, um sie zu benennen — oder wähle mehrere aus und führe sie zusammen.',

    // Loose faces
    'people.singleFaces': 'Einzelne Gesichter',
    'people.singleFacesHint': 'Häkchen zum Auswählen, Bild antippen zum Zuordnen. Unbekannte einfach auswählen und ausblenden.',
    'people.selectPage': 'Seite auswählen',
    'people.showHiddenFaces': 'Ausgeblendete',

    // Hidden faces
    'people.hiddenFaces': 'Ausgeblendete Gesichter',
    'people.unhideAll': 'Alle wieder einblenden',
    'people.unhide': 'Wieder einblenden',

    // Selection bars
    'people.selectedCount': '{count} ausgewählt',
    'people.merge': 'Zusammenführen',
    'people.hide': 'Verbergen',
    'people.clearSelection': 'Auswahl aufheben',
    'people.facesCount': '{count} Gesicht(er)',
    'people.hideFaces': 'Ausblenden',
    'people.toPerson': 'Zu Person…',

    // Big-face overlay
    'people.adoptFallback': 'Übernehmen',
    'people.suggestionLine': 'Vorschlag: {name} · Ähnlichkeit {percent}%',

    // Toasts
    'people.toastFacesHidden': '{count} Gesicht(er) ausgeblendet',
    'people.toastFacesShown': '{count} Gesicht(er) wieder eingeblendet',
    'people.toastPersonDeleted': 'Person gelöscht',
    'people.toastClusterStarted': 'Clustering gestartet… (läuft im Hintergrund, Ergebnis erscheint gleich)',
    'people.toastClusterFailed': 'Clustering konnte nicht gestartet werden',
    'people.toastWriteFacesQueued': 'Gesichts-Regionen werden in {count} Foto(s) geschrieben',
    'people.toastWriteFacesFailed': 'Gesichter-Schreiben fehlgeschlagen',
    'people.toastDetectStarted': 'Lokale Gesichtserkennung gestartet für {count} Bild(er)',
    'people.toastDetectFailed': 'Lokale Gesichtserkennung fehlgeschlagen',
    'people.toastConfirmed': '{count} Gesicht(er) bestätigt',
    'people.toastRejected': '{count} Vorschlag/Vorschläge abgelehnt',
    'people.toastSuggestQueued': 'Vorschläge werden berechnet — erscheinen in Kürze.',
    'people.toastWarmCropsQueued': 'Crop-Cache wird vorbereitet ({count} Gesichter) — die Personen-Seite wird danach sofort schnell',
    'people.toastWarmCropsFailed': 'Crop-Cache vorbereiten fehlgeschlagen',
    'people.toastPersonsHidden': '{count} Person(en) verborgen',
    'people.toastPersonsShown': '{count} Person(en) eingeblendet',
    'people.toastPersonCreated': 'Person erstellt',
    'people.toastPeopleMerged': '{count} Person(en) zusammengeführt',

    // Delete confirm
    'people.deleteConfirmTitle': '"{name}" löschen?',
    'people.deleteConfirmMessage': 'Die Gesichter werden wieder freigegeben.',
    'people.deleteLabel': 'Löschen',
    'people.unknown': 'Unbekannt',

    // Pager
    'people.perPage': 'Pro Seite:',
    'people.pagerRange': '{from}–{to} von {total}',
    'people.pagerPrev': '‹ Zurück',
    'people.pagerPage': 'Seite {page} / {pages}',
    'people.pagerNext': 'Weiter ›',

    // FaceTile
    'people.assignFace': 'Gesicht zuordnen',
    'people.deselect': 'Abwählen',
    'people.selectOne': 'Auswählen',
    'people.showWholePhoto': 'Ganzes Foto anzeigen',

    // PersonCard
    'people.toggleHiddenShow': 'Wieder einblenden',
    'people.toggleHiddenHide': 'Verbergen / Ignorieren',
    'people.deleteTitle': 'Löschen',
    'people.hiddenBadge': 'verborgen',
    'people.namePlaceholderMerge': 'Name… (bekannte = zusammenführen)',
    'people.rename': 'Umbenennen',
    'people.addName': '+ Name hinzufügen',
    'people.photosCountOne': '{n} Foto',
    'people.photosCountMany': '{n} Fotos',
    'people.ageSuffix': ' · {age} J.',
    'people.toastMergedInto': 'Mit „{name}" zusammengeführt',
    'people.toastNameSaved': 'Name gespeichert',
    'people.toastSaveFailed': 'Speichern fehlgeschlagen',

    // Empty
    'people.emptyTitle': 'Noch keine Personen',
    'people.emptyHint': 'Starte die KI-Pipeline für automatische Gesichtserkennung oder füge Personen manuell hinzu.',

    // Detail view
    'people.back': 'Zurück',
    'people.unnamedPerson': 'Unbenannte Person',
    'people.edit': 'Bearbeiten',
    'people.addNameLink': '+ Namen vergeben',
    'people.photos': '{count} Fotos',
    'people.born': '· geb. {date} ({age} J.)',
    'people.showAgain': 'Wieder anzeigen',
    'people.hideOne': 'Verbergen',
    'people.deletePerson': 'Person löschen',
    'people.toastSaved': 'Gespeichert',
    'people.toastCoverSet': 'Titelbild gesetzt',
    'people.toastFaceRemoved': 'Gesicht entfernt',

    // Detail tabs
    'people.detailTabPhotos': 'Fotos',
    'people.detailTabFaces': 'Gesichter',
    'people.detailTabRelations': 'Beziehungen',

    // Photos tab
    'people.photoSortNewest': 'Neueste',
    'people.photoSortOldest': 'Älteste',
    'people.noPhotosYet': 'Noch keine Fotos — Gesichtserkennung läuft beim Verarbeiten.',

    // Faces tab
    'people.noFacesAssigned': 'Noch keine Gesichter zugeordnet.',
    'people.facesTabHint': 'Tippe ★ um ein Gesicht als Profilbild zu setzen · ✕ entfernt es von dieser Person.',
    'people.setAsProfile': 'Als Profilbild',
    'people.removeFaceConfirmTitle': 'Gehört nicht zu dieser Person?',
    'people.removeFaceConfirmMessage': 'Das Gesicht wird wieder freigegeben.',
    'people.notThisPerson': 'Ist nicht diese Person',

    // Relationships
    'people.relParent': 'Elternteil von',
    'people.relGrandparent': 'Großelternteil von',
    'people.relPartner': 'Partner',
    'people.relSibling': 'Geschwister',
    'people.relRelative': 'Verwandt',
    'people.relFriend': 'Freund/in',
    'people.relColleague': 'Kollege/in',
    'people.relOther': 'Verbindung',
    'people.relMapHeading': 'Beziehungs-Map',
    'people.relMore': '+{count} weitere — in der Liste unten',
    'people.relationships': 'Beziehungen ({count})',
    'people.addConnection': '+ Verbindung',
    'people.createFamilyAlbum': 'Familien-Album erstellen',
    'people.relPersonIs': '{name} ist',
    'people.searchPersonCount': 'Person suchen … ({count})',
    'people.noMatches': 'keine Treffer',
    'people.addConnectionBtn': 'Hinzufügen',
    'people.noConnections': 'Noch keine Verbindungen. Lege über „+ Verbindung“ Familie, Freunde oder Kollegen an.',
    'people.removeConnectionConfirm': 'Verbindung entfernen?',
    'people.removeLabel': 'Entfernen',
    'people.toastConnectionAdded': 'Verbindung hinzugefügt',
    'people.familyAlbumName': 'Familie {name}',
    'people.toastFamilyAlbumCreated': 'Smart-Album „Familie …" erstellt',

    // EditPersonForm
    'people.namePlaceholder': 'Name',
    'people.nicknamePlaceholder': 'Spitzname',
    'people.birthdateTitle': 'Geburtsdatum',
    'people.notesPlaceholder': 'Notizen',
    'people.emailPlaceholder': 'E-Mail',
    'people.phonePlaceholder': 'Telefon',
    'people.addressPlaceholder': 'Adresse',
    'people.cancel': 'Abbrechen',
    'people.save': 'Speichern',

    // MergeModal
    'people.mergeModalTitle': '{count} Personen zusammenführen',
    'people.mergeModalIntro': 'Wähle die Person, die behalten wird. Alle Gesichter der anderen werden zu ihr verschoben.',
    'people.keepBadge': 'behalten',
    'people.mergeNameLabel': 'Name nach dem Zusammenführen',
    'people.nameOptional': 'Name (optional)',
    'people.toastMergeFailed': 'Zusammenführen fehlgeschlagen',
    'people.photosShort': '{count} Fotos',

    // FaceAssignModal
    'people.assignOneFace': 'Gesicht zuordnen',
    'people.assignManyFaces': '{count} Gesichter zuordnen',
    'people.newPersonFromFace': 'Neue Person aus diesem Gesicht',
    'people.newPersonFromFaces': 'Neue Person aus {count} Gesichtern',
    'people.new': 'Neu',
    'people.orToExisting': '…oder zu vorhandener Person',
    'people.searchPerson': 'Person suchen…',
    'people.noNamedPeople': 'Keine benannten Personen.',
    'people.toastFacesAssigned': '{count} Gesicht(er) zugeordnet',
    'people.toastAssignFailed': 'Zuordnen fehlgeschlagen',
    'people.toastNewPersonCreated': 'Neue Person erstellt',
    'people.toastCreateFailed': 'Erstellen fehlgeschlagen',

    // AddPersonModal
    'people.addPersonTitle': 'Person hinzufügen',
    'people.nameRequired': 'Name *',
    'people.aliasNickname': 'Alias / Spitzname',
    'people.birthdateOptional': 'Geburtsdatum (optional)',
    'people.addPersonTip': 'Tipp: Personen entstehen normalerweise automatisch aus erkannten Gesichtern. Manuell angelegte Personen haben zunächst keine Fotos.',
    'people.creating': 'Erstelle…',

    // QuickNameOverlay
    'people.qnTitle': 'Schnell benennen',
    'people.qnProgress': '{named} benannt · {left} übrig',
    'people.qnDone': 'Fertig! 🎉',
    'people.qnDoneCount': '{count} Personen benannt.',
    'people.qnClose': 'Schließen',
    'people.qnFacesPhotos': '{faces} Gesichter · {photos} Fotos',
    'people.qnInputPlaceholder': 'Name eingeben + Enter',
    'people.qnNameBtn': 'Benennen',
    'people.qnSkip': 'Überspringen',
    'people.qnDissolveTitle': 'Keine echte Person / kein Gesicht — Gruppe auflösen',
    'people.qnDissolve': 'Auflösen',
    'people.qnHint': 'Enter = benennen · Tab = überspringen',
    'people.qnToastSaveFailed': 'Konnte nicht speichern',
    'people.qnToastDissolveFailed': 'Konnte nicht auflösen',
  } as Record<string, string>,
  en: {
    // Header / list
    'people.title': 'People',
    'people.subtitleNamedUnknown': '{named} named · {unknown} unknown',
    'people.cropsProgress': ' · Crops {cached}/{total}',
    'people.sortTitle': 'Sort people',
    'people.sortMostPhotos': 'Most photos',
    'people.sortLeastPhotos': 'Fewest photos',
    'people.sortMostFaces': 'Most faces',
    'people.sortName': 'Name (A–Z)',
    'people.sortRecent': 'Recently added',
    'people.quickNameTitle': 'Quickly name unnamed groups',
    'people.quickName': 'Quick name',
    'people.done': 'Done',
    'people.selectMergeTitle': 'Select multiple people to merge or hide them',
    'people.selectMerge': 'Select / Merge',
    'people.select': 'Select',
    'people.hideHiddenTitle': 'Hide hidden',
    'people.showHiddenTitle': 'Show hidden',
    'people.hidden': 'Hidden',
    'people.clusterTitle': 'Automatically group unassigned faces',
    'people.clustering': 'Clustering…',
    'people.cluster': 'Cluster',
    'people.detectFacesTitle': 'Detect faces locally on the server (in parallel with descriptions) — finishes faster, independent of the AI backlog',
    'people.starting': 'Starting…',
    'people.detectFaces': 'Detect faces',
    'people.warmCropsTitle': 'Pre-generate all face thumbnails (crops) — the People page then loads instantly without running ffmpeg per video face',
    'people.warmCrops': 'Prepare crops',
    'people.writeFacesTitle': 'Permanently write all detected faces (coordinates + names) into the image files (MWG regions) — avoids re-running face detection later',
    'people.writing': 'Writing…',
    'people.writeFaces': 'Write faces',
    'people.add': 'Add',

    // Select-mode banner
    'people.selectBanner': 'Select people (tap them). With 2 or more you can merge or hide them below.',

    // Help details
    'people.helpSummary': 'What do the actions above do?',
    'people.helpSummaryNote': '(everything also runs automatically)',
    'people.helpDetect': 'Detect faces & Cluster: run automatically in the background (detection ongoing, grouping at night). The buttons just trigger it immediately — you normally don’t need to press them.',
    'people.helpQuickName': 'Quick name: quickly name unknown groups. If you type an already known name, the group is merged with that person instead of creating a duplicate.',
    'people.helpWarmCrops': 'Prepare crops: pre-generates the face thumbnails (page loads faster afterwards). Optional.',
    'people.helpWriteFaces': 'Write faces: stores names permanently in the image files (for re-import). Optional.',

    // Loading / empty
    'people.loading': 'Loading…',

    // Tabs
    'people.tabPeople': 'People ({count})',
    'people.tabUnknown': 'Unknown ({count})',
    'people.tabSuggestions': 'Suggestions',
    'people.tabSuggestionsCount': 'Suggestions ({count})',
    'people.tabUnknownFaces': 'Unknown faces',
    'people.tabUnknownFacesCount': 'Unknown faces ({count})',
    'people.tabHidden': 'Hidden',

    // Suggestions
    'people.noOpenSuggestions': 'No open suggestions. New ones appear automatically (or "Recalculate" in the pipeline).',
    'people.suggestionsHeading': 'Suggestions — "Is this …?"',
    'people.suggestionsHint': 'Uncertain matches that ArcFace does not assign automatically. ✓ accept · ✗ discard.',
    'people.recalculating': 'Calculating…',
    'people.recalculate': 'Recalculate',
    'people.confirmAll': 'Confirm all',
    'people.rejectAll': 'Reject all',
    'people.rejectGroupConfirmTitle': 'Reject all {count} suggestions for "{name}"?',
    'people.rejectGroupConfirmMessage': 'The faces will not be assigned (only the suggestion is removed).',
    'people.adopt': 'Accept',
    'people.discard': 'Discard',

    // Sections
    'people.namedPeople': 'Named people',
    'people.unknownPeople': 'Unknown people',
    'people.unknownPeopleHint': 'Click a person to name them — or select several and merge them.',

    // Loose faces
    'people.singleFaces': 'Individual faces',
    'people.singleFacesHint': 'Check to select, tap an image to assign. Just select unknown ones and hide them.',
    'people.selectPage': 'Select page',
    'people.showHiddenFaces': 'Hidden',

    // Hidden faces
    'people.hiddenFaces': 'Hidden faces',
    'people.unhideAll': 'Show all again',
    'people.unhide': 'Show again',

    // Selection bars
    'people.selectedCount': '{count} selected',
    'people.merge': 'Merge',
    'people.hide': 'Hide',
    'people.clearSelection': 'Clear selection',
    'people.facesCount': '{count} face(s)',
    'people.hideFaces': 'Hide',
    'people.toPerson': 'To person…',

    // Big-face overlay
    'people.adoptFallback': 'Accept',
    'people.suggestionLine': 'Suggestion: {name} · similarity {percent}%',

    // Toasts
    'people.toastFacesHidden': '{count} face(s) hidden',
    'people.toastFacesShown': '{count} face(s) shown again',
    'people.toastPersonDeleted': 'Person deleted',
    'people.toastClusterStarted': 'Clustering started… (runs in the background, result appears shortly)',
    'people.toastClusterFailed': 'Clustering could not be started',
    'people.toastWriteFacesQueued': 'Face regions are being written into {count} photo(s)',
    'people.toastWriteFacesFailed': 'Writing faces failed',
    'people.toastDetectStarted': 'Local face detection started for {count} image(s)',
    'people.toastDetectFailed': 'Local face detection failed',
    'people.toastConfirmed': '{count} face(s) confirmed',
    'people.toastRejected': '{count} suggestion(s) rejected',
    'people.toastSuggestQueued': 'Suggestions are being calculated — appearing shortly.',
    'people.toastWarmCropsQueued': 'Crop cache is being prepared ({count} faces) — the People page will be instant afterwards',
    'people.toastWarmCropsFailed': 'Preparing crop cache failed',
    'people.toastPersonsHidden': '{count} person(s) hidden',
    'people.toastPersonsShown': '{count} person(s) shown',
    'people.toastPersonCreated': 'Person created',
    'people.toastPeopleMerged': '{count} person(s) merged',

    // Delete confirm
    'people.deleteConfirmTitle': 'Delete "{name}"?',
    'people.deleteConfirmMessage': 'The faces will be released again.',
    'people.deleteLabel': 'Delete',
    'people.unknown': 'Unknown',

    // Pager
    'people.perPage': 'Per page:',
    'people.pagerRange': '{from}–{to} of {total}',
    'people.pagerPrev': '‹ Back',
    'people.pagerPage': 'Page {page} / {pages}',
    'people.pagerNext': 'Next ›',

    // FaceTile
    'people.assignFace': 'Assign face',
    'people.deselect': 'Deselect',
    'people.selectOne': 'Select',
    'people.showWholePhoto': 'Show whole photo',

    // PersonCard
    'people.toggleHiddenShow': 'Show again',
    'people.toggleHiddenHide': 'Hide / Ignore',
    'people.deleteTitle': 'Delete',
    'people.hiddenBadge': 'hidden',
    'people.namePlaceholderMerge': 'Name… (known = merge)',
    'people.rename': 'Rename',
    'people.addName': '+ Add name',
    'people.photosCountOne': '{n} photo',
    'people.photosCountMany': '{n} photos',
    'people.ageSuffix': ' · age {age}',
    'people.toastMergedInto': 'Merged with "{name}"',
    'people.toastNameSaved': 'Name saved',
    'people.toastSaveFailed': 'Saving failed',

    // Empty
    'people.emptyTitle': 'No people yet',
    'people.emptyHint': 'Start the AI pipeline for automatic face detection or add people manually.',

    // Detail view
    'people.back': 'Back',
    'people.unnamedPerson': 'Unnamed person',
    'people.edit': 'Edit',
    'people.addNameLink': '+ Add name',
    'people.photos': '{count} photos',
    'people.born': '· born {date} (age {age})',
    'people.showAgain': 'Show again',
    'people.hideOne': 'Hide',
    'people.deletePerson': 'Delete person',
    'people.toastSaved': 'Saved',
    'people.toastCoverSet': 'Cover image set',
    'people.toastFaceRemoved': 'Face removed',

    // Detail tabs
    'people.detailTabPhotos': 'Photos',
    'people.detailTabFaces': 'Faces',
    'people.detailTabRelations': 'Relationships',

    // Photos tab
    'people.photoSortNewest': 'Newest',
    'people.photoSortOldest': 'Oldest',
    'people.noPhotosYet': 'No photos yet — face detection runs during processing.',

    // Faces tab
    'people.noFacesAssigned': 'No faces assigned yet.',
    'people.facesTabHint': 'Tap ★ to set a face as the profile picture · ✕ removes it from this person.',
    'people.setAsProfile': 'As profile picture',
    'people.removeFaceConfirmTitle': 'Not this person?',
    'people.removeFaceConfirmMessage': 'The face will be released again.',
    'people.notThisPerson': 'Not this person',

    // Relationships
    'people.relParent': 'Parent of',
    'people.relGrandparent': 'Grandparent of',
    'people.relPartner': 'Partner',
    'people.relSibling': 'Sibling',
    'people.relRelative': 'Related',
    'people.relFriend': 'Friend',
    'people.relColleague': 'Colleague',
    'people.relOther': 'Connection',
    'people.relMapHeading': 'Relationship map',
    'people.relMore': '+{count} more — in the list below',
    'people.relationships': 'Relationships ({count})',
    'people.addConnection': '+ Connection',
    'people.createFamilyAlbum': 'Create family album',
    'people.relPersonIs': '{name} is',
    'people.searchPersonCount': 'Search person … ({count})',
    'people.noMatches': 'no matches',
    'people.addConnectionBtn': 'Add',
    'people.noConnections': 'No connections yet. Use "+ Connection" to add family, friends or colleagues.',
    'people.removeConnectionConfirm': 'Remove connection?',
    'people.removeLabel': 'Remove',
    'people.toastConnectionAdded': 'Connection added',
    'people.familyAlbumName': 'Family {name}',
    'people.toastFamilyAlbumCreated': 'Smart album "Family …" created',

    // EditPersonForm
    'people.namePlaceholder': 'Name',
    'people.nicknamePlaceholder': 'Nickname',
    'people.birthdateTitle': 'Birthdate',
    'people.notesPlaceholder': 'Notes',
    'people.emailPlaceholder': 'Email',
    'people.phonePlaceholder': 'Phone',
    'people.addressPlaceholder': 'Address',
    'people.cancel': 'Cancel',
    'people.save': 'Save',

    // MergeModal
    'people.mergeModalTitle': 'Merge {count} people',
    'people.mergeModalIntro': 'Choose the person to keep. All faces of the others will be moved to them.',
    'people.keepBadge': 'keep',
    'people.mergeNameLabel': 'Name after merging',
    'people.nameOptional': 'Name (optional)',
    'people.toastMergeFailed': 'Merging failed',
    'people.photosShort': '{count} photos',

    // FaceAssignModal
    'people.assignOneFace': 'Assign face',
    'people.assignManyFaces': 'Assign {count} faces',
    'people.newPersonFromFace': 'New person from this face',
    'people.newPersonFromFaces': 'New person from {count} faces',
    'people.new': 'New',
    'people.orToExisting': '…or to an existing person',
    'people.searchPerson': 'Search person…',
    'people.noNamedPeople': 'No named people.',
    'people.toastFacesAssigned': '{count} face(s) assigned',
    'people.toastAssignFailed': 'Assigning failed',
    'people.toastNewPersonCreated': 'New person created',
    'people.toastCreateFailed': 'Creating failed',

    // AddPersonModal
    'people.addPersonTitle': 'Add person',
    'people.nameRequired': 'Name *',
    'people.aliasNickname': 'Alias / Nickname',
    'people.birthdateOptional': 'Birthdate (optional)',
    'people.addPersonTip': 'Tip: People are usually created automatically from detected faces. Manually created people have no photos at first.',
    'people.creating': 'Creating…',

    // QuickNameOverlay
    'people.qnTitle': 'Quick name',
    'people.qnProgress': '{named} named · {left} left',
    'people.qnDone': 'Done! 🎉',
    'people.qnDoneCount': '{count} people named.',
    'people.qnClose': 'Close',
    'people.qnFacesPhotos': '{faces} faces · {photos} photos',
    'people.qnInputPlaceholder': 'Enter name + Enter',
    'people.qnNameBtn': 'Name',
    'people.qnSkip': 'Skip',
    'people.qnDissolveTitle': 'Not a real person / no face — dissolve group',
    'people.qnDissolve': 'Dissolve',
    'people.qnHint': 'Enter = name · Tab = skip',
    'people.qnToastSaveFailed': 'Could not save',
    'people.qnToastDissolveFailed': 'Could not dissolve',
  } as Record<string, string>,
}
