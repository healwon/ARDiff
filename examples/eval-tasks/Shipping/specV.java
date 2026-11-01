public class specV {
    // spec: the old rule, free from 80, and express adds 7 on top (also when shipping is free)
    public static double snippet(int weight, int total, int express) {
        int fee = 0;
        fee = 5;
        if (weight > 10) {
            fee = fee + (weight - 10) / 2;
        }
        if (total >= 80) {
            fee = 0;
        }
        if (express == 1) {
            fee = fee + 7;
        }
        return fee;
    }
}
