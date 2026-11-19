export const SIMULATION_MESSAGE_LANGUAGE_ENABLED = import.meta.env?.VITE_SIMULATION_MESSAGE_LANGUAGE !== 'false'

export const SIMULATION_MESSAGE_LOCATIONS_KN = Object.freeze({
  Madikeri: 'ಮಡಿಕೇರಿ',
  Virajpet: 'ವಿರಾಜಪೇಟೆ',
  Chittalli: 'ಚಿಟ್ಟಳ್ಳಿ',
  Perumbadi: 'ಪೆರುಂಬಾಡಿ',
  Makutta: 'ಮಾಕುಟ್ಟ',
})

export const SIMULATION_MESSAGE_TEMPLATES = Object.freeze({
  en: Object.freeze({
    LOW: 'SIMULATION ONLY — LANDsense SIMULATION ALERT: Low landslide risk simulated in {location}. Please stay alert, avoid unstable slopes, and follow the recommended safer route.',
    MODERATE: 'SIMULATION ONLY — LANDsense SIMULATION ALERT: Moderate landslide risk simulated in {location}. Please stay alert, avoid unstable slopes, and follow the recommended safer route.',
    HIGH: 'SIMULATION ONLY — LANDsense SIMULATION ALERT: High landslide risk simulated in {location}. Please stay alert, avoid unstable slopes, and follow the recommended safer route.',
    CRITICAL: 'SIMULATION ONLY — LANDsense SIMULATION ALERT: Critical landslide risk simulated in {location}. Move away from unstable slopes and follow the recommended safer route.',
  }),
  kn: Object.freeze({
    LOW: 'ಸಿಮ್ಯುಲೇಶನ್ ಮಾತ್ರ — LANDsense ಸಿಮ್ಯುಲೇಶನ್ ಮಾಹಿತಿ: {location_kn}ಯಲ್ಲಿ ಕಡಿಮೆ ಭೂಕುಸಿತ ಅಪಾಯವನ್ನು ಅನುಕರಿಸಲಾಗಿದೆ. ದಯವಿಟ್ಟು ಎಚ್ಚರಿಕೆಯಿಂದಿರಿ, ಅಸ್ಥಿರ ಇಳಿಜಾರುಗಳಿಂದ ದೂರವಿರಿ ಮತ್ತು ಶಿಫಾರಸು ಮಾಡಿದ ಸುರಕ್ಷಿತ ಮಾರ್ಗವನ್ನು ಅನುಸರಿಸಿ.',
    MODERATE: 'ಸಿಮ್ಯುಲೇಶನ್ ಮಾತ್ರ — LANDsense ಸಿಮ್ಯುಲೇಶನ್ ಎಚ್ಚರಿಕೆ: {location_kn}ಯಲ್ಲಿ ಮಧ್ಯಮ ಭೂಕುಸಿತ ಅಪಾಯವನ್ನು ಅನುಕರಿಸಲಾಗಿದೆ. ದಯವಿಟ್ಟು ಎಚ್ಚರಿಕೆಯಿಂದಿರಿ, ಅಸ್ಥಿರ ಇಳಿಜಾರುಗಳಿಂದ ದೂರವಿರಿ ಮತ್ತು ಶಿಫಾರಸು ಮಾಡಿದ ಸುರಕ್ಷಿತ ಮಾರ್ಗವನ್ನು ಅನುಸರಿಸಿ.',
    HIGH: 'ಸಿಮ್ಯುಲೇಶನ್ ಮಾತ್ರ — LANDsense ಸಿಮ್ಯುಲೇಶನ್ ಎಚ್ಚರಿಕೆ: {location_kn}ಯಲ್ಲಿ ಹೆಚ್ಚಿನ ಭೂಕುಸಿತ ಅಪಾಯವನ್ನು ಅನುಕರಿಸಲಾಗಿದೆ. ದಯವಿಟ್ಟು ಎಚ್ಚರಿಕೆಯಿಂದಿರಿ, ಅಸ್ಥಿರ ಇಳಿಜಾರುಗಳಿಂದ ದೂರವಿರಿ ಮತ್ತು ಶಿಫಾರಸು ಮಾಡಿದ ಸುರಕ್ಷಿತ ಮಾರ್ಗವನ್ನು ಅನುಸರಿಸಿ.',
    CRITICAL: 'ಸಿಮ್ಯುಲೇಶನ್ ಮಾತ್ರ — LANDsense ಸಿಮ್ಯುಲೇಶನ್ ಎಚ್ಚರಿಕೆ: {location_kn}ಯಲ್ಲಿ ಅತ್ಯಂತ ಹೆಚ್ಚಿನ ಭೂಕುಸಿತ ಅಪಾಯವನ್ನು ಅನುಕರಿಸಲಾಗಿದೆ. ಅಸ್ಥಿರ ಇಳಿಜಾರುಗಳಿಂದ ದೂರ ಸರಿದು ಶಿಫಾರಸು ಮಾಡಿದ ಸುರಕ್ಷಿತ ಮಾರ್ಗವನ್ನು ಅನುಸರಿಸಿ.',
  }),
})
