import dev.omalauncher.widgets.lang.*;
import java.nio.file.*;
import java.util.*;

// Evaluates a widget with the reference implementation (owl.jar) against a
// fixture, and prints every node's evaluated properties and every Canvas's
// drawing calls as JSON, for comparison with Owl.js.
public class OwlOracle {
  static Obj fixture;
  static Program program;
  static Value[] cache;
  static Env root;

  static Value fx(String key) {
    Value v = fixture.getFields().get(key);
    return v == null ? Null.INSTANCE : v;
  }

  static Value field(Value o, String key) {
    if (!(o instanceof Obj)) return Null.INSTANCE;
    Value v = ((Obj) o).getFields().get(key);
    return v == null ? Null.INSTANCE : v;
  }

  static final Host HOST = new Host() {
    final Budget budget = new Budget(200000);
    public Budget getBudget() { return budget; }
    public Value read(int slot) {
      if (cache[slot] != null) return cache[slot];
      Global g = program.getGlobals().get(slot);
      Value v;
      if (g instanceof Global.Source) {
        Global.Source s = (Global.Source) g;
        Value e = field(fx("sources"), s.getName());
        if (e instanceof Obj && ((Obj) e).getFields().containsKey("value")) v = field(e, "value");
        else if (e instanceof Obj && ((Obj) e).getFields().containsKey("text")) {
          String t = field(e, "text").toString();
          if (s.getJson()) {
            try { v = Json.INSTANCE.parse(t.trim()); } catch (RuntimeException x) { v = Null.INSTANCE; }
          } else v = Json.INSTANCE.parse(quote(t.replaceAll("\\s+$", "")));
        } else v = Null.INSTANCE;
      } else if (g instanceof Global.State) {
        v = ((Global.State) g).getInit().invoke(root);
      } else if (g instanceof Global.Let) {
        v = ((Global.Let) g).getValue().invoke(root);
      } else if (g instanceof Global.Sampled) {
        Global.Sampled s = (Global.Sampled) g;
        Value one = s.getOf().invoke(root);
        v = s.getPrev() ? Null.INSTANCE : new Lst(Collections.singletonList(one));
      } else if (g instanceof Global.Asset) {
        // Owl.js turns an embedded image into a data URL. Match that, or the
        // first widget with an asset fails the runtime comparison.
        byte[] bytes = ((Global.Asset) g).getBytes();
        String b64 = Base64.getEncoder().encodeToString(bytes);
        v = Json.INSTANCE.parse(quote("data:" + assetMime(b64) + ";base64," + b64));
      } else {
        v = Null.INSTANCE;
      }
      cache[slot] = v;
      return v;
    }
    public void write(int slot, Value value) {}
    public Integer theme(String name) {
      Value v = field(fx("theme"), name);
      return v == Null.INSTANCE ? null : (int) Long.parseLong(v.toString());
    }
    public double time() { return Double.parseDouble(fx("time").toString()); }
    public Value tile(String name) { return field(fx("tile"), name); }
    public void act(String name, List<? extends Value> args) {}
    public void report(String message) { System.err.println("report: " + message); }
  };

  static String assetMime(String b64) {
    if (b64.startsWith("iVBOR")) return "image/png";
    if (b64.startsWith("/9j/")) return "image/jpeg";
    if (b64.startsWith("R0lG")) return "image/gif";
    if (b64.startsWith("UklGR")) return "image/webp";
    if (b64.startsWith("PHN2") || b64.startsWith("PD94")) return "image/svg+xml";
    return "application/octet-stream";
  }

  static String quote(String s) {
    StringBuilder b = new StringBuilder("\"");
    for (char c : s.toCharArray()) {
      if (c == '"' || c == '\\') b.append('\\').append(c);
      else if (c == '\n') b.append("\\n");
      else if (c == '\r') b.append("\\r");
      else if (c == '\t') b.append("\\t");
      else if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
      else b.append(c);
    }
    return b.append('"').toString();
  }

  static String show(Ev ev, Env env) {
    try {
      return quote(ev.invoke(env).toString());
    } catch (RuntimeException e) {
      return quote("ERROR " + e.getMessage());
    }
  }

  static boolean truthy(Ev ev, Env env) {
    try { return ev.invoke(env).getTruthy(); } catch (RuntimeException e) { return false; }
  }

  static List<Value> items(Value v) {
    if (v instanceof Lst) return ((Lst) v).getItems();
    if (v instanceof Obj) return new ArrayList<>(((Obj) v).getFields().values());
    if (v == Null.INSTANCE) return Collections.emptyList();
    return Collections.singletonList(v);
  }

  static void nodes(List<WNode> list, Env env, StringBuilder out) {
    for (WNode n : list) node(n, env, out);
  }

  static void sep(StringBuilder out) {
    char last = out.charAt(out.length() - 1);
    if (last != '[' && last != '{') out.append(',');
  }

  static void props(Map<String, Ev> props, Env env, StringBuilder out) {
    out.append('{');
    boolean first = true;
    for (String k : new TreeSet<>(props.keySet())) {
      if (!first) out.append(',');
      first = false;
      out.append(quote(k)).append(':').append(show(props.get(k), env));
    }
    out.append('}');
  }

  static void node(WNode n, Env env, StringBuilder out) {
    if (n instanceof WNode.Lets) {
      nodes(((WNode.Lets) n).getChildren(), env.lets(((WNode.Lets) n).getValues()), out);
    } else if (n instanceof WNode.If) {
      WNode.If i = (WNode.If) n;
      nodes(truthy(i.getCond(), env) ? i.getThen() : i.getOrElse(), env, out);
    } else if (n instanceof WNode.For) {
      WNode.For f = (WNode.For) n;
      Value list;
      try { list = f.getList().invoke(env); } catch (RuntimeException e) { list = Null.INSTANCE; }
      List<Value> its = items(list);
      for (int i = 0; i < its.size() && i < 1000; i++)
        nodes(f.getBody(), env.child(its.get(i), Json.INSTANCE.parse(String.valueOf(i))), out);
    } else if (n instanceof WNode.Use) {
      WNode.Use u = (WNode.Use) n;
      Value[] args = new Value[u.getArgs().size()];
      for (int i = 0; i < args.length; i++) {
        try { args[i] = u.getArgs().get(i).invoke(env); } catch (RuntimeException e) { args[i] = Null.INSTANCE; }
      }
      Env inner = new Env(HOST, new Env(HOST, null, new Object[0]), args);
      if (u.getWrapper().isEmpty()) {
        nodes(u.getBody(), inner, out);
      } else {
        sep(out);
        out.append("{\"kind\":\"Box\",\"props\":");
        props(u.getWrapper(), env, out);
        out.append(",\"children\":[");
        nodes(u.getBody(), inner, out);
        out.append("]}");
      }
    } else if (n instanceof WNode.Element) {
      WNode.Element e = (WNode.Element) n;
      sep(out);
      out.append("{\"kind\":").append(quote(e.getKind())).append(",\"props\":");
      props(e.getProps(), env, out);
      out.append(",\"anim\":");
      props(e.getAnimations(), env, out);
      if (e.getKind().equals("Canvas")) {
        Value[] size = { Json.INSTANCE.parse(fx("canvas").toString().replaceAll("[\\[\\]]", "").split(", ")[0]),
          Json.INSTANCE.parse(fx("canvas").toString().replaceAll("[\\[\\]]", "").split(", ")[1]) };
        out.append(",\"draw\":[");
        draws(e.getChildren(), env.child(size), out);
        out.append("]");
      } else {
        out.append(",\"children\":[");
        nodes(e.getChildren(), env, out);
        out.append("]");
      }
      out.append('}');
    }
  }

  static void draws(List<WNode> nodesIn, Env env, StringBuilder out) {
    for (WNode n : nodesIn) {
      if (n instanceof WNode.Lets) draws(((WNode.Lets) n).getChildren(), env.lets(((WNode.Lets) n).getValues()), out);
      else if (n instanceof WNode.If) {
        WNode.If i = (WNode.If) n;
        draws(truthy(i.getCond(), env) ? i.getThen() : i.getOrElse(), env, out);
      } else if (n instanceof WNode.For) {
        WNode.For f = (WNode.For) n;
        Value list;
        try { list = f.getList().invoke(env); } catch (RuntimeException e) { list = Null.INSTANCE; }
        List<Value> its = items(list);
        for (int i = 0; i < its.size() && i < 1000; i++)
          draws(f.getBody(), env.child(its.get(i), Json.INSTANCE.parse(String.valueOf(i))), out);
      } else if (n instanceof WNode.Draw) {
        WNode.Draw d = (WNode.Draw) n;
        sep(out);
        out.append("{\"op\":").append(quote(d.getOp())).append(",\"args\":[");
        for (int i = 0; i < d.getArgs().size(); i++) {
          if (i > 0) out.append(',');
          out.append(show(d.getArgs().get(i), env));
        }
        out.append("],\"named\":");
        props(d.getNamed(), env, out);
        if (d.getChildren() != null) {
          out.append(",\"ops\":[");
          draws(d.getChildren(), env, out);
          out.append("]");
        }
        out.append('}');
      }
    }
  }

  // random() and shuffle(list) in a state's first value draw the same numbers
  // here and in walk.js, or a face that deals from a shuffled bag, like tetris,
  // shows a different next piece on each side.
  static class Fixed extends kotlin.random.Random {
    double x = 0;
    public double nextDouble() { x = (x + 0.6180339887498949) % 1; return x; }
    public int nextBits(int bits) { return (int) (nextDouble() * (1L << bits)); }
  }

  static void fixRandom() throws Exception {
    java.lang.reflect.Field f = sun.misc.Unsafe.class.getDeclaredField("theUnsafe");
    f.setAccessible(true);
    sun.misc.Unsafe u = (sun.misc.Unsafe) f.get(null);
    java.lang.reflect.Field d = kotlin.random.Random.class.getDeclaredField("defaultRandom");
    u.putObject(u.staticFieldBase(d), u.staticFieldOffset(d), new Fixed());
  }

  public static void main(String[] a) throws Exception {
    fixRandom();
    String src = new String(Files.readAllBytes(Paths.get(a[0])), "UTF-8");
    fixture = (Obj) Json.INSTANCE.parse(new String(Files.readAllBytes(Paths.get(a[1])), "UTF-8"));
    program = dev.omalauncher.widgets.lang.Compiler.Companion.compile(src, "en");
    cache = new Value[program.getGlobals().size()];
    root = Env.Companion.root(HOST);
    // What the file says about itself: where it goes, and a face's status bar.
    StringBuilder out = new StringBuilder("{\"program\":{\"face\":" + program.isFace() + ",\"page\":" + program.getPage()
      + ",\"order\":" + program.getOrder() + ",\"padding\":" + quote(Json.INSTANCE.parse(String.valueOf(program.getPadding())).toString())
      + ",\"background\":" + (program.getBackground() == null ? "null" : show(program.getBackground(), root))
      + ",\"statusBar\":" + (program.getStatusBar() == null ? "null" : show(program.getStatusBar(), root)) + "},\"root\":[");
    nodes(program.getRoot(), root, out);
    out.append("]");
    if (program.getScreen() != null) {
      out.append(",\"screen\":[");
      nodes(program.getScreen(), root, out);
      out.append("]");
    }
    out.append("}");
    System.out.println(out);
  }
}
