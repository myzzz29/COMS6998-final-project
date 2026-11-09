//! Bounded egg saturation with separately certified, design-specific ground rules.
//! This is proof-carrying normalization, not an SMT solver or stimulus generator.
use egg::{define_language, rewrite, AstSize, Extractor, Id, Pattern, RecExpr, Rewrite, Runner, Symbol};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::{io::{self, Read}, time::{Duration, Instant}};

define_language! {
    enum Bool { "true" = True, "false" = False, "not" = Not(Id),
                "and" = And([Id; 2]), "or" = Or([Id; 2]), Var(Symbol), }
}
fn main() {
    let total_start = Instant::now();
    let mode = std::env::args().nth(1).unwrap_or_else(|| "baseline".into());
    assert!(["baseline", "representatives", "spanning"].contains(&mode.as_str()));
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let data: Value = serde_json::from_str(&input).unwrap();
    let targets = data["targets"].as_array().unwrap();
    let mut rules: Vec<Rewrite<Bool, ()>> = vec![
        rewrite!("de-morgan-or"; "(not (or ?a ?b))" => "(and (not ?a) (not ?b))"),
        rewrite!("de-morgan-and"; "(not (and ?a ?b))" => "(or (not ?a) (not ?b))"),
        rewrite!("double-not"; "(not (not ?a))" => "?a"),
        rewrite!("and-true"; "(and ?a true)" => "?a"),
        rewrite!("and-true-left"; "(and true ?a)" => "?a"),
        rewrite!("not-false"; "(not false)" => "true"),
    ];
    for rule in data["verified_rules"].as_array().unwrap() {
        assert_eq!(rule["proof_status"], "unsat");
        let a: Pattern<Bool> = rule["left"].as_str().unwrap().parse().unwrap();
        let b: Pattern<Bool> = rule["right"].as_str().unwrap().parse().unwrap();
        rules.push(Rewrite::new(rule["name"].as_str().unwrap(), a, b).unwrap());
    }
    let mut runner = Runner::<Bool, ()>::default().with_explanations_enabled()
        .with_iter_limit(20).with_node_limit(20000).with_time_limit(Duration::from_secs(5));
    let expressions: Vec<RecExpr<Bool>> = targets.iter().map(|t| t["compact"].as_str().unwrap().parse().unwrap()).collect();
    for e in &expressions { runner = runner.with_expr(e); }
    runner.egraph.rebuild();
    let before: Vec<_> = runner.roots.iter().map(|r| usize::from(runner.egraph.find(*r))).collect();
    let build_seconds = total_start.elapsed().as_secs_f64();
    let start = Instant::now();
    runner = runner.run(&rules);
    let elapsed = start.elapsed().as_secs_f64();
    let roots: Vec<_> = runner.roots.iter().map(|r| usize::from(runner.egraph.find(*r))).collect();
    let extraction_start = Instant::now();
    let extractor = Extractor::new(&runner.egraph, AstSize);
    let mut cache = HashMap::new();
    let mut normalized = Vec::new();
    for (i, t) in targets.iter().enumerate() {
        let representative = if mode == "baseline" {
            extractor.find_best(Id::from(roots[i])).1.to_string()
        } else {
            cache.entry(roots[i]).or_insert_with(|| extractor.find_best(Id::from(roots[i])).1.to_string()).clone()
        };
        normalized.push(json!({"id":t["id"], "eclass_before":before[i], "eclass":roots[i], "representative":representative}));
    }
    let extraction_seconds = extraction_start.elapsed().as_secs_f64();
    let explanation_start = Instant::now();
    let mut pairs = Vec::new();
    if mode == "spanning" {
        // Each old component is structurally identical; connect ALL target vertices
        // when at least two old components merge, preserving baseline connectivity.
        let mut groups: std::collections::BTreeMap<(usize, String), Vec<usize>> = std::collections::BTreeMap::new();
        for i in 0..targets.len() {
            groups.entry((roots[i], targets[i]["event_context"].to_string())).or_default().push(i);
        }
        for members in groups.values() {
            let a = members[0];
            if let Some(&b) = members.iter().find(|&&i| before[i] != before[a]) {
                for &i in members.iter().skip(1) {
                    pairs.push(if before[i] != before[a] { (a, i) } else { (b, i) });
                }
            }
        }
    } else {
        for i in 0..targets.len() {
            for j in i+1..targets.len() {
                if roots[i] == roots[j] && before[i] != before[j] && targets[i]["event_context"] == targets[j]["event_context"] {
                    pairs.push((i,j));
                }
            }
        }
    }
    let mut evidence = Vec::new();
    for (i, j) in pairs {
        evidence.push(json!({"left":targets[i]["id"], "right":targets[j]["id"],
            "explanation":runner.explain_equivalence(&expressions[i], &expressions[j]).get_flat_string()}));
    }
    let explanation_seconds = explanation_start.elapsed().as_secs_f64();
    let serialization_start = Instant::now();
    let output = serde_json::to_string_pretty(&json!({
        "engine":"egg 0.11.0", "method":"six Boolean rules plus independently QF_BV-proven ground rules; no unconditional manual unions",
        "targets":normalized, "rewrite_explanations":evidence, "iterations":runner.iterations.len(),
        "stop_reason":format!("{:?}",runner.stop_reason), "saturation_seconds":elapsed,
        "eclasses":runner.egraph.number_of_classes(), "enodes":runner.egraph.total_size(),
        "ground_rule_count":data["verified_rules"].as_array().unwrap().len()
    })).unwrap();
    let serialization_seconds = serialization_start.elapsed().as_secs_f64();
    println!("{}", output);
    eprintln!("{}", json!({"mode":mode, "build_seconds":build_seconds,
        "saturation_seconds":elapsed, "extraction_seconds":extraction_seconds,
        "explanation_seconds":explanation_seconds, "serialization_seconds":serialization_seconds,
        "total_seconds":total_start.elapsed().as_secs_f64()}));
}
