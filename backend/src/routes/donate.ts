import Router from "@koa/router";
import Stripe from "stripe";
import { config } from "../config.js";

export const donateRouter = new Router();

donateRouter.post("/donate", async (ctx) => {
  if (!config.stripeSecretKey) {
    ctx.status = 503;
    ctx.body = { msg: "Donations not configured" };
    return;
  }

  const stripe = new Stripe(config.stripeSecretKey);

  const paymentIntent = await stripe.paymentIntents.create({
    amount: 100, // $1.00 in cents
    currency: "usd",
    description: "ChatRAG Donation",
    automatic_payment_methods: { enabled: true },
  });

  ctx.body = { clientSecret: paymentIntent.client_secret };
});
