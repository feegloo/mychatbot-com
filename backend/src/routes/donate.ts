import Router from '@koa/router'
import Stripe from 'stripe'
import { config } from '../config.js'

export const donateRouter = new Router()

/** Create a PaymentIntent for Apple Pay (native PaymentRequest API flow) */
donateRouter.post('/donate', async (ctx) => {
  if (!config.stripeSecretKey) {
    ctx.status = 503
    ctx.body = { msg: 'Donations not configured' }
    return
  }

  const stripe = new Stripe(config.stripeSecretKey)
  const body = ctx.request.body as { amount?: number }
  const amountCents = Math.round(Math.min(Math.max(Math.floor(body.amount ?? 1), 1), 1000) * 100)

  const paymentIntent = await stripe.paymentIntents.create({
    amount: amountCents,
    currency: 'usd',
    description: 'ChatRAG Donation',
    automatic_payment_methods: { enabled: true },
  })

  ctx.body = { clientSecret: paymentIntent.client_secret }
})

/** Create a Stripe Checkout Session for non-Apple Pay methods */
donateRouter.post('/donate/checkout', async (ctx) => {
  if (!config.stripeSecretKey) {
    ctx.status = 503
    ctx.body = { msg: 'Donations not configured' }
    return
  }

  const stripe = new Stripe(config.stripeSecretKey)
  const body = ctx.request.body as { returnUrl?: string; amount?: number }
  const returnUrl = body.returnUrl || 'https://chatrag.app'
  const amountCents = Math.round(Math.min(Math.max(Math.floor(body.amount ?? 1), 1), 1000) * 100)

  const session = await stripe.checkout.sessions.create({
    mode: 'payment',
    line_items: [
      {
        price_data: {
          currency: 'usd',
          product_data: { name: 'ChatRAG Donation' },
          unit_amount: amountCents,
        },
        quantity: 1,
      },
    ],
    success_url: `${returnUrl}?donated=1`,
    cancel_url: returnUrl,
  })

  ctx.body = { url: session.url }
})

/** Check if a Checkout Session payment succeeded (for frontend confirmation) */
donateRouter.get('/donate/status/:sessionId', async (ctx) => {
  if (!config.stripeSecretKey) {
    ctx.status = 503
    ctx.body = { msg: 'Donations not configured' }
    return
  }

  const stripe = new Stripe(config.stripeSecretKey)
  const session = await stripe.checkout.sessions.retrieve(ctx.params.sessionId)
  ctx.body = { status: session.payment_status }
})
