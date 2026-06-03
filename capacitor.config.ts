import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'pl.mekamb.music',
  appName: 'Mekamb Music',
  webDir: 'client-dist',
  ios: {
    scheme: 'MekambMusic',
  },
  plugins: {
    CapacitorHttp: {
      enabled: true,
    },
  },
}

export default config
