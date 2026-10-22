import bcrypt from "bcryptjs";
import type { NextFunction, Request, Response } from "express";
import jwt from "jsonwebtoken";
import { env, isProd } from "./config.js";
import { User } from "./models/misc.js";

const COOKIE = "mapster_token";

export async function seedAdmin() {
  const email = env.ADMIN_EMAIL.toLowerCase();
  const hash = await bcrypt.hash(env.ADMIN_PASSWORD, 12);
  const existing = await User.findOne({ email });
  if (!existing) await User.create({ email, passwordHash: hash });
  else if (!(await bcrypt.compare(env.ADMIN_PASSWORD, existing.passwordHash!))) await User.updateOne({ email }, { passwordHash: hash });
}

export async function login(email: string, password: string, res: Response) {
  const u = await User.findOne({ email: email.toLowerCase() });
  if (!u || !(await bcrypt.compare(password, u.passwordHash!))) return false;
  const token = jwt.sign({ sub: u.id, email: u.email }, env.JWT_SECRET, { expiresIn: "7d" });
  res.cookie(COOKIE, token, { httpOnly: true, sameSite: "strict", secure: isProd, maxAge: 7 * 864e5 });
  return true;
}

export const logout = (res: Response) => void res.clearCookie(COOKIE);

export function requireAuth(req: Request, res: Response, next: NextFunction) {
  try {
    (req as Request & { user?: unknown }).user = jwt.verify(req.cookies?.[COOKIE] ?? "", env.JWT_SECRET);
    next();
  } catch {
    res.status(401).json({ error: "Not signed in" });
  }
}
