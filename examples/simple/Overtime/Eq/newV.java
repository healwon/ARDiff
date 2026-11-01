public class newV {
    // bonus tested on whole tens of pay: pay always ends in 5, so pay / 10 > 40 exactly when pay > 405
    public static double snippet(int hours) {
        int base = 0;
        int pay = 0;
        int bonus = 0;
        base = hours * 10;
        pay = base + 5;
        if (pay / 10 > 40) {
            bonus = 1;
        }
        return bonus;
    }
}
