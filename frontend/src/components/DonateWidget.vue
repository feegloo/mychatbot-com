<template>
  <div class="donate-widget">
    <!-- Thank you message -->
    <div v-if="thankYou" class="donate-thanks">Thank you for donation!</div>

    <!-- Payment method bubbles -->
    <div v-else-if="showMethods" class="donate-methods">
      <button
        v-for="m in availableMethods"
        :key="m.id"
        class="donate-bubble"
        :title="m.label"
        @click="handleMethodClick(m)"
      >
        <span class="donate-bubble-icon" v-html="m.icon"></span>
      </button>
    </div>

    <!-- Default donate button -->
    <button v-else-if="canDonate" class="conv-nav-donate" @click="handleDonate">Donate 1$</button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { loadStripe, type Stripe, type PaymentRequest } from '@stripe/stripe-js'
import axios from 'axios'

const api = axios.create({
  // @ts-ignore
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:3000/api',
})

// @ts-ignore
const stripeKey = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY as string

const route = useRoute()
const thankYou = ref(false)
const showMethods = ref(false)
const hasApplePay = ref(false)

let stripeInstance: Stripe | null = null
let paymentRequest: PaymentRequest | null = null

interface PaymentMethod {
  id: string
  label: string
  icon: string
  native?: boolean // uses PaymentRequest API
}

const allMethods: PaymentMethod[] = [
  {
    id: 'apple_pay',
    label: 'Apple Pay',
    native: true,
    icon: `<svg viewBox="0 0 24 24" fill="currentColor" width="24" height="24"><path d="M17.05 20.28c-.98.95-2.05.88-3.08.4-1.09-.5-2.08-.52-3.23 0-1.44.64-2.2.46-3.06-.4C3.79 16.17 4.36 9.53 8.77 9.28c1.25.06 2.13.7 2.87.73.97-.2 1.9-.77 2.93-.7 1.24.1 2.17.58 2.78 1.48-2.54 1.52-1.94 4.87.3 5.8-.56 1.47-1.28 2.92-2.6 4.69zM12.05 9.2c-.15-2.23 1.66-4.07 3.74-4.2.29 2.58-2.34 4.5-3.74 4.2z"/></svg>`,
  },
  {
    id: 'google_pay',
    label: 'Google Pay',
    icon: `<svg viewBox="0 0 24 24" width="24" height="24"><path fill="#4285F4" d="M21.58 12.22c0-.66-.06-1.3-.16-1.92H12v3.63h5.38a4.6 4.6 0 01-2 3.02v2.5h3.24c1.89-1.74 2.96-4.3 2.96-7.23z"/><path fill="#34A853" d="M12 22c2.7 0 4.96-.9 6.62-2.42l-3.24-2.5c-.9.6-2.04.96-3.38.96-2.6 0-4.8-1.76-5.58-4.12H3.1v2.58A9.99 9.99 0 0012 22z"/><path fill="#FBBC05" d="M6.42 14.06a5.98 5.98 0 010-3.82V7.66H3.1a9.99 9.99 0 000 8.98l3.32-2.58z"/><path fill="#EA4335" d="M12 6.08c1.47 0 2.78.5 3.82 1.5l2.86-2.86C16.96 3.13 14.7 2.2 12 2.2A9.99 9.99 0 003.1 7.66l3.32 2.58C7.2 7.84 9.4 6.08 12 6.08z"/></svg>`,
  },
  {
    id: 'card',
    label: 'Card',
    icon: `<svg viewBox="0 0 24 24" fill="currentColor" width="24" height="24"><path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 14H4v-6h16v6zm0-10H4V6h16v2z"/></svg>`,
  },
  {
    id: 'blik',
    label: 'BLIK',
    icon: `<svg viewBox="0 0 24 24" width="24" height="24"><circle cx="12" cy="12" r="10" fill="#000"/><text x="12" y="16" text-anchor="middle" fill="#fff" font-size="8" font-weight="bold">BLIK</text></svg>`,
  },
  {
    id: 'p24',
    label: 'Przelewy24',
    icon: `<svg viewBox="0 0 24 24" width="24" height="24"><rect width="24" height="24" rx="4" fill="#d42027"/><text x="12" y="16" text-anchor="middle" fill="#fff" font-size="8" font-weight="bold">P24</text></svg>`,
  },
  {
    id: 'paypal',
    label: 'PayPal',
    icon: `<svg viewBox="0 0 24 24" width="24" height="24"><path fill="#003087" d="M7.02 21.5l.4-2.48h-1L8.07 8.54a.3.3 0 01.3-.26h4.65c1.54 0 2.75.32 3.54 1.06.37.35.63.76.78 1.22.16.48.2 1.05.1 1.72l-.01.06v.48l.37.2c.31.17.56.36.75.58.27.32.44.72.5 1.18.07.47.03 1.03-.1 1.65-.16.72-.42 1.35-.78 1.87-.33.48-.75.87-1.24 1.16-.46.27-1 .47-1.6.58-.58.1-1.22.16-1.92.16H13a.94.94 0 00-.93.8l-.02.12-.38 2.42-.02.09a.3.3 0 01-.3.26H7.02z"/><path fill="#0070E0" d="M18.15 10.38c-.01.05-.02.1-.03.16-.76 3.9-3.36 5.25-6.68 5.25h-1.7a.82.82 0 00-.81.69l-.87 5.5-.24 1.55a.43.43 0 00.43.5h3a.72.72 0 00.71-.61l.03-.15.56-3.55.04-.2a.72.72 0 01.71-.61h.45c2.9 0 5.16-1.17 5.82-4.58.28-1.42.13-2.61-.6-3.44a2.87 2.87 0 00-.82-.51z"/></svg>`,
  },
  {
    id: 'bancontact',
    label: 'Bancontact',
    icon: `<svg viewBox="0 0 24 24" width="24" height="24"><rect width="24" height="24" rx="4" fill="#005498"/><text x="12" y="16" text-anchor="middle" fill="#fff" font-size="7" font-weight="bold">BC</text></svg>`,
  },
  {
    id: 'klarna',
    label: 'Klarna',
    icon: `<svg viewBox="0 0 24 24" width="24" height="24"><rect width="24" height="24" rx="4" fill="#FFB3C7"/><text x="12" y="16" text-anchor="middle" fill="#0A0B09" font-size="7" font-weight="bold">K</text></svg>`,
  },
  {
    id: 'eps',
    label: 'EPS',
    icon: `<svg viewBox="0 0 24 24" width="24" height="24"><rect width="24" height="24" rx="4" fill="#6C1D5F"/><text x="12" y="16" text-anchor="middle" fill="#fff" font-size="8" font-weight="bold">EPS</text></svg>`,
  },
  {
    id: 'link',
    label: 'Link',
    icon: `<svg viewBox="0 0 24 24" width="24" height="24"><rect width="24" height="24" rx="4" fill="#00D66E"/><text x="12" y="16" text-anchor="middle" fill="#fff" font-size="8" font-weight="bold">⚡</text></svg>`,
  },
]

const availableMethods = computed(() => {
  return allMethods.filter((m) => {
    if (m.id === 'apple_pay') return hasApplePay.value
    return true // Stripe Checkout handles availability dynamically
  })
})

const canDonate = computed(() => {
  return !!stripeKey
})

async function initStripe() {
  if (!stripeKey) return

  stripeInstance = await loadStripe(stripeKey)
  if (!stripeInstance) return

  paymentRequest = stripeInstance.paymentRequest({
    country: 'US',
    currency: 'usd',
    total: { label: 'ChatRAG Donation', amount: 100 },
    requestPayerName: false,
    requestPayerEmail: false,
  })

  const result = await paymentRequest.canMakePayment()
  if (result?.applePay) {
    hasApplePay.value = true

    paymentRequest.on('paymentmethod', async (ev) => {
      try {
        const { data } = await api.post('/donate')
        const { error } = await stripeInstance!.confirmCardPayment(
          data.clientSecret,
          { payment_method: ev.paymentMethod.id },
          { handleActions: false },
        )
        if (error) {
          ev.complete('fail')
        } else {
          ev.complete('success')
          showThankYou()
        }
      } catch {
        ev.complete('fail')
      }
    })
  }
}

function handleDonate() {
  if (hasApplePay.value && paymentRequest) {
    // Try Apple Pay first; if user cancels, show methods
    const cancelHandler = () => {
      paymentRequest!.off('cancel', cancelHandler)
      showMethods.value = true
    }
    paymentRequest.on('cancel', cancelHandler)
    paymentRequest.show()
  } else {
    // No Apple Pay — show payment methods immediately
    showMethods.value = true
  }
}

async function handleMethodClick(method: PaymentMethod) {
  if (method.native && method.id === 'apple_pay' && paymentRequest) {
    paymentRequest.show()
    return
  }

  // All other methods → Stripe Checkout
  try {
    const returnUrl = window.location.origin + window.location.pathname
    const { data } = await api.post('/donate/checkout', { returnUrl })
    if (data.url) {
      window.location.href = data.url
    }
  } catch {
    // silently fail
  }
}

function showThankYou() {
  thankYou.value = true
  showMethods.value = false
  setTimeout(() => {
    thankYou.value = false
  }, 10000)
}

function checkDonateSuccess() {
  const params = new URLSearchParams(window.location.search)
  if (params.get('donated') === '1') {
    showThankYou()
    // Clean up URL
    const url = new URL(window.location.href)
    url.searchParams.delete('donated')
    window.history.replaceState({}, '', url.pathname + url.search)
  }
}

onMounted(() => {
  initStripe()
  checkDonateSuccess()
})
</script>
