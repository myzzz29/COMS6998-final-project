//! Bounded egg saturation with separately certified, design-specific ground rules.
//! This is proof-carrying normalization, not an SMT solver or stimulus generator.
use egg::{define_language, rewrite, AstSize, Extractor, Id, Pattern, RecExpr, Rewrite, Runner, Symbol};
use serde_json::{json, Value};
use std::{io::{self, Read}, time::{Duration, Instant}};

define_language! {
    enum Bool { "true" = True, "false" = False, "not" = Not(Id),
                "and" = And([Id; 2]), "or" = Or([Id; 2]), Var(Symbol), }
}
fn main() {
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
    let start = Instant::now();
    runner = runner.run(&rules);
    let elapsed = start.elapsed().as_secs_f64();
    let roots: Vec<_> = runner.roots.iter().map(|r| usize::from(runner.egraph.find(*r))).collect();
    let extractor = Extractor::new(&runner.egraph, AstSize);
    let normalized: Vec<_> = targets.iter().enumerate().map(|(i, t)| json!({
        "id":t["id"], "eclass_before":before[i], "eclass":roots[i],
        "representative":extractor.find_best(Id::from(roots[i])).1.to_string()})).collect();
    let mut evidence = Vec::new();
    for i in 0..targets.len() {
        for j in i+1..targets.len() {
            if roots[i] == roots[j] && before[i] != before[j] && targets[i]["event_context"] == targets[j]["event_context"] {
                evidence.push(json!({"left":targets[i]["id"], "right":targets[j]["id"],
                    "explanation":runner.explain_equivalence(&expressions[i], &expressions[j]).get_flat_string()}));
            }
        }
    }
    println!("{}", serde_json::to_string_pretty(&json!({
        "engine":"egg 0.11.0", "method":"six Boolean rules plus independently QF_BV-proven ground rules; no unconditional manual unions",
        "targets":normalized, "rewrite_explanations":evidence, "iterations":runner.iterations.len(),
        "stop_reason":format!("{:?}",runner.stop_reason), "saturation_seconds":elapsed,
        "eclasses":runner.egraph.number_of_classes(), "enodes":runner.egraph.total_size(),
        "ground_rule_count":data["verified_rules"].as_array().unwrap().len()
    })).unwrap());
}
